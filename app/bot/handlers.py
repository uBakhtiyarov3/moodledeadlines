import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from aiogram import BaseMiddleware, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject
from sqlalchemy import delete, select

from app.bot import rich
from app.bot.keyboards import admin_kb, lang_kb, main_kb, open_app_kb
from app.config import get_settings
from app.db import Session
from app.i18n import T, humanize_left, t
from app.models import ChatMessage, Deadline, User
from app.moodle.ical import IcalUrlError
from app.services import ai, linking, tts, users
from app.services import settings as rt

router = Router()
# The bot only talks in private chats (it may be added to groups for broadcasts later)
router.message.filter(F.chat.type == "private")
EXPORT_RE = re.compile(r"(?:https?|webcal)://\S*calendar/export_execute\.php\S*", re.I)


class UserMiddleware(BaseMiddleware):
    """Registers the user, enforces bans and maintenance mode, injects `user`."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        tg = data.get("event_from_user")
        if tg is None:
            return await handler(event, data)
        user, created = await users.upsert(tg.id, tg.first_name, tg.username, tg.language_code)
        data["user"], data["created"] = user, created
        answer = getattr(event, "answer", None)
        if user.is_banned:
            if answer:
                await answer(t("banned", user.lang))
            return None
        if rt.get("maintenance") and not users.is_admin(user):
            if answer:
                await answer(t("maintenance", user.lang))
            return None
        return await handler(event, data)


def _texts(key: str) -> set[str]:
    return set(T[key].values())


@router.message(CommandStart())
async def start(message: Message, user: User, created: bool):
    if created:
        await message.answer(t("choose_lang", user.lang), reply_markup=lang_kb())
        return
    await send_welcome(message, user)


async def send_welcome(message: Message, user: User):
    name = rich.esc(user.first_name or "talaba")
    await rich.send(message.bot, message.chat.id, t("welcome_md", user.lang, name=name), main_kb(user.lang))
    kb = open_app_kb(user.lang, "" if user.ical_url_enc else "connect")
    if kb:
        await message.answer("👇", reply_markup=kb)


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(cb: CallbackQuery, user: User):
    lang = cb.data.split(":", 1)[1]
    async with Session() as s:
        u = await s.get(User, user.id)
        u.lang = lang
        await s.commit()
    user.lang = lang
    await cb.answer(t("lang_set", lang))
    await cb.message.delete()
    await send_welcome(cb.message, user)


@router.message(Command("lang"))
@router.message(F.text.in_(_texts("btn_lang")))
async def ask_lang(message: Message, user: User):
    await message.answer(t("choose_lang", user.lang), reply_markup=lang_kb())


@router.message(Command("admin"))
async def admin(message: Message, user: User):
    if users.is_admin(user):
        kb = admin_kb(user.lang)
        await message.answer("🛠" if kb else t("app_unavailable", user.lang), reply_markup=kb)


@router.message(F.text.in_(_texts("btn_settings")))
@router.message(Command("settings"))
async def open_settings(message: Message, user: User):
    kb = open_app_kb(user.lang, "settings", "open_settings")
    await message.answer(t("settings_hint" if kb else "app_unavailable", user.lang), reply_markup=kb)


@router.message(Command("deadlines"))
@router.message(F.text.in_(_texts("btn_deadlines")))
async def list_deadlines(message: Message, user: User):
    if not user.ical_url_enc:
        await message.answer(t("connect_hint", user.lang), reply_markup=open_app_kb(user.lang, "connect"))
        return
    now = datetime.now(timezone.utc)
    async with Session() as s:
        rows = (
            await s.execute(
                select(Deadline)
                .where(
                    Deadline.user_id == user.id,
                    Deadline.due_at > now,
                    Deadline.completed.is_(False),
                    Deadline.hidden.is_(False),
                    Deadline.gone.is_(False),
                )
                .order_by(Deadline.due_at)
                .limit(10)
            )
        ).scalars().all()
    if not rows:
        await message.answer(t("no_deadlines", user.lang), reply_markup=open_app_kb(user.lang))
        return
    await rich.send(message.bot, message.chat.id, deadlines_markdown(rows, user.lang, now),
                    open_app_kb(user.lang, "deadlines"))


def deadlines_markdown(rows: list[Deadline], lang: str, now: datetime) -> str:
    """Rich table; dates render in each student's own language and timezone."""
    tz = ZoneInfo(get_settings().timezone)
    lines = [t("dl_title", lang), "", t("dl_cols", lang), "|:-:|:--|:--|:--|"]
    for d in rows:
        left = int((d.due_at - now).total_seconds() // 60)
        dot = "🔴" if left < 360 else "🟠" if left < 1440 else "🟢"
        local = d.due_at.astimezone(tz)
        task = f"**{rich.esc(d.title)}**" + (f"<br>*{rich.esc(d.course)}*" if d.course else "")
        due = rich.tg_time(d.due_at, "wDT", f"{local:%d.%m %H:%M}")
        rel = rich.tg_time(d.due_at, "r", humanize_left(left, lang))
        lines.append(f"| {dot} | {task} | {due} | {rel} |")
    lines += ["", f"<sub>{t('dl_legend', lang)}</sub>"]
    return "\n".join(lines)


@router.callback_query(F.data.startswith("done:"))
async def mark_done(cb: CallbackQuery, user: User):
    did = int(cb.data.split(":", 1)[1])
    async with Session() as s:
        d = await s.get(Deadline, did)
        if d and d.user_id == user.id:
            d.completed = True
            await s.commit()
    await cb.answer(t("marked_done", user.lang), show_alert=False)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.reply(t("marked_done", user.lang))


@router.message(F.text.func(lambda s: bool(EXPORT_RE.search(s))))
async def link_from_chat(message: Message, user: User):
    url = EXPORT_RE.search(message.text).group(0)
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        n = await linking.link_ical(user.id, url)
    except IcalUrlError as e:
        await message.answer(t(f"err_{e.args[0]}", user.lang))
        return
    except httpx.HTTPError:
        await message.answer(t("err_network", user.lang))
        return
    try:
        await message.delete()  # the link contains a private token
    except Exception:  # noqa: BLE001
        pass
    await message.answer(t("linked_ok", user.lang, n=n), reply_markup=open_app_kb(user.lang, "deadlines"))


@router.message(F.text.in_(_texts("btn_ai")))
@router.message(Command("ai"))
async def ai_intro(message: Message, user: User):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("btn_new_chat", user.lang), callback_data="ai:new")]]
    )
    await message.answer(t("ai_intro", user.lang), reply_markup=kb)


async def _clear_chat(user_id: int) -> None:
    async with Session() as s:
        await s.execute(delete(ChatMessage).where(ChatMessage.user_id == user_id))
        await s.commit()


@router.message(Command("new"))
async def ai_new(message: Message, user: User):
    await _clear_chat(user.id)
    await message.answer(t("ai_new", user.lang))


@router.callback_query(F.data == "ai:new")
async def ai_new_cb(cb: CallbackQuery, user: User):
    await _clear_chat(user.id)
    await cb.answer()
    await cb.message.answer(t("ai_new", user.lang))


AI_ERRORS = {"disabled": "ai_disabled", "limit": "ai_limit", "busy": "ai_busy", "unsupported": "unsupported_file"}
MAX_FILE = 15 * 1024 * 1024


async def _answer_ai(message: Message, user: User, text: str, media: list | None = None, voice: bool = False):
    """Stream the answer live as a rich draft, then send it as a rich message."""
    try:
        answer = await rich.stream(
            message.bot, message.chat.id, ai.ask_stream(user, text, media), thinking=t("thinking", user.lang)
        )
    except ai.AIUnavailable as e:
        await message.answer(t(AI_ERRORS.get(e.code, "ai_error"), user.lang))
        return
    await rich.send(message.bot, message.chat.id, answer.strip() or "…")
    # Asked by voice → also answer by voice (text first, so nobody waits for the audio)
    if voice and tts.enabled():
        await message.bot.send_chat_action(message.chat.id, ChatAction.RECORD_VOICE)
        ogg = await tts.synthesize(answer)
        if ogg:
            await message.answer_voice(BufferedInputFile(ogg, "pulse.ogg"))


@router.message(F.text & ~F.text.startswith("/"))
async def ai_chat(message: Message, user: User):
    await _answer_ai(message, user, message.text)


async def download(bot, file_id: str) -> bytes:
    buf = await bot.download(file_id)
    return buf.read()


def media_spec(message: Message) -> tuple[str, str, str, int, int] | None:
    """(kind, mime, file_id, size, duration) for supported attachments."""
    if message.voice:
        v = message.voice
        return "audio", v.mime_type or "audio/ogg", v.file_id, v.file_size or 0, v.duration
    if message.audio:
        a = message.audio
        return "audio", a.mime_type or "audio/mpeg", a.file_id, a.file_size or 0, a.duration
    if message.photo:
        p = message.photo[-1]
        return "image", "image/jpeg", p.file_id, p.file_size or 0, 0
    if message.document:
        d = message.document
        mime = d.mime_type or ""
        if mime in ("image/jpeg", "image/png", "image/webp"):
            return "image", mime, d.file_id, d.file_size or 0, 0
        if mime == "application/pdf":
            return "document", mime, d.file_id, d.file_size or 0, 0
    return None


@router.message(F.voice | F.audio | F.photo | F.document)
async def ai_media(message: Message, user: User):
    spec = media_spec(message)
    if spec is None:
        await message.answer(t("unsupported_file", user.lang))
        return
    kind, mime, file_id, size, duration = spec
    limit = get_settings().ai_max_voice_sec
    if kind == "audio" and duration > limit:
        await message.answer(t("voice_too_long", user.lang, n=limit // 60))
        return
    if size > MAX_FILE:
        await message.answer(t("file_too_big", user.lang))
        return
    await message.bot.send_chat_action(
        message.chat.id, ChatAction.RECORD_VOICE if kind == "audio" else ChatAction.TYPING
    )
    data = await download(message.bot, file_id)
    await _answer_ai(
        message, user, message.caption or "", [ai.Media(kind, mime, data)], voice=bool(message.voice)
    )


@router.message()
async def non_text(message: Message, user: User):
    await message.answer(t("unsupported_file", user.lang))


def split_message(text: str, limit: int = 3500) -> list[str]:
    """Split on paragraph/line boundaries so Markdown markers aren't cut in half."""
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts or [text]
