import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from aiogram import BaseMiddleware, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject
from sqlalchemy import delete, select

from app.bot.keyboards import admin_kb, lang_kb, main_kb, open_app_kb
from app.config import get_settings
from app.db import Session
from app.i18n import T, humanize_left, t
from app.models import ChatMessage, Deadline, User
from app.moodle.ical import IcalUrlError
from app.services import ai, linking, users
from app.services import settings as rt
from app.services.tg_html import markdown_to_tg

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
    await message.answer(
        t("welcome", user.lang, name=html.escape(user.first_name or "talaba")),
        reply_markup=main_kb(user.lang),
    )
    section = "" if user.ical_url_enc else "connect"
    await message.answer("👇", reply_markup=open_app_kb(user.lang, section))


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
        await message.answer("🛠", reply_markup=admin_kb(user.lang))


@router.message(Command("deadlines"))
@router.message(F.text.in_(_texts("btn_deadlines")))
async def list_deadlines(message: Message, user: User):
    if not user.ical_url_enc:
        await message.answer(t("connect_hint", user.lang), reply_markup=open_app_kb(user.lang, "connect"))
        return
    now = datetime.now(timezone.utc)
    tz = ZoneInfo(get_settings().timezone)
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
    lines = [t("deadlines_head", user.lang), ""]
    for d in rows:
        left = int((d.due_at - now).total_seconds() // 60)
        dot = "🔴" if left < 360 else "🟠" if left < 1440 else "🟢"
        lines.append(f"{dot} <b>{html.escape(d.title)}</b>")
        if d.course:
            lines.append(f"    🎓 {html.escape(d.course)}")
        lines.append(f"    🕒 {d.due_at.astimezone(tz):%d.%m %H:%M} · {humanize_left(left, user.lang)}")
    await message.answer("\n".join(lines), reply_markup=open_app_kb(user.lang, "deadlines"))


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


@router.message(F.text & ~F.text.startswith("/"))
async def ai_chat(message: Message, user: User):
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        answer = await ai.ask(user, message.text)
    except ai.AIUnavailable as e:
        key = {"disabled": "ai_disabled", "limit": "ai_limit"}.get(e.code, "ai_error")
        await message.answer(t(key, user.lang))
        return
    for part in split_message(answer):
        try:
            await message.answer(markdown_to_tg(part), disable_web_page_preview=True)
        except Exception:  # noqa: BLE001  (unexpected markup → send as plain text)
            await message.answer(part, parse_mode=None, disable_web_page_preview=True)


@router.message(~F.text)
async def non_text(message: Message, user: User):
    await message.answer(t("text_only", user.lang))


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
