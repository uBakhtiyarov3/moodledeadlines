"""Student ↔ admin support chat.

Students write from the bot ("💬 Admin bilan chat" mode) or from the Mini App chat page.
Every admin gets the message as a rich card and can answer by replying to it, by tapping
"↩️ Javob berish", or from the admin Mini App. Answers reach the student in Telegram and
appear in the Mini App chat.
"""

import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendRichMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputRichMessage, WebAppInfo
from sqlalchemy import delete, func, select, update

from app.db import Session
from app.i18n import t
from app.models import SupportMessage, SupportRelay, SupportState, User, utcnow
from app.services import users

log = logging.getLogger(__name__)

MAX_LEN = 3500


# ---------------------------------------------------------------- state

async def get_state(user_id: int) -> SupportState | None:
    async with Session() as s:
        return await s.get(SupportState, user_id)


async def set_state(user_id: int, mode: str | None, target: int | None = None) -> None:
    async with Session() as s:
        if mode is None:
            await s.execute(delete(SupportState).where(SupportState.user_id == user_id))
        else:
            await s.merge(SupportState(user_id=user_id, mode=mode, target_user_id=target, updated_at=utcnow()))
        await s.commit()


# ---------------------------------------------------------------- storage / queries

async def add(user_id: int, text: str, from_admin: bool, admin_id: int | None = None) -> SupportMessage:
    async with Session() as s:
        m = SupportMessage(user_id=user_id, text=text[:MAX_LEN], from_admin=from_admin, admin_id=admin_id)
        s.add(m)
        await s.commit()
        await s.refresh(m)
        return m


async def thread(user_id: int, limit: int = 200) -> list[SupportMessage]:
    async with Session() as s:
        rows = (
            await s.execute(
                select(SupportMessage).where(SupportMessage.user_id == user_id)
                .order_by(SupportMessage.id.desc()).limit(limit)
            )
        ).scalars().all()
    return rows[::-1]


async def mark_read(user_id: int, by_admin: bool) -> None:
    """by_admin=True: admin read the student's messages; False: student read admin's."""
    async with Session() as s:
        await s.execute(
            update(SupportMessage)
            .where(SupportMessage.user_id == user_id, SupportMessage.from_admin.is_(not by_admin),
                   SupportMessage.read.is_(False))
            .values(read=True)
        )
        await s.commit()


async def unread_for_student(user_id: int) -> int:
    async with Session() as s:
        return (await s.execute(
            select(func.count(SupportMessage.id)).where(
                SupportMessage.user_id == user_id, SupportMessage.from_admin.is_(True), SupportMessage.read.is_(False))
        )).scalar_one()


async def threads() -> list[dict]:
    """Inbox for admins: one row per student, newest activity first."""
    async with Session() as s:
        last = (
            select(SupportMessage.user_id, func.max(SupportMessage.id).label("last_id"))
            .group_by(SupportMessage.user_id).subquery()
        )
        unread = (
            select(SupportMessage.user_id, func.count(SupportMessage.id).label("n"))
            .where(SupportMessage.from_admin.is_(False), SupportMessage.read.is_(False))
            .group_by(SupportMessage.user_id).subquery()
        )
        rows = (
            await s.execute(
                select(SupportMessage, User, unread.c.n)
                .join(last, SupportMessage.id == last.c.last_id)
                .join(User, User.id == SupportMessage.user_id)
                .outerjoin(unread, unread.c.user_id == SupportMessage.user_id)
                .order_by(SupportMessage.id.desc())
            )
        ).all()
    return [
        {
            "user_id": u.id, "first_name": u.first_name, "username": u.username, "lang": u.lang,
            "last_text": m.text[:140], "last_from_admin": m.from_admin,
            "last_at": m.created_at.isoformat(), "unread": n or 0,
        }
        for m, u, n in rows
    ]


async def unread_total_for_admins() -> int:
    async with Session() as s:
        return (await s.execute(
            select(func.count(SupportMessage.id)).where(
                SupportMessage.from_admin.is_(False), SupportMessage.read.is_(False))
        )).scalar_one()


# ---------------------------------------------------------------- rich cards

def _esc(text: str) -> str:
    from app.bot.rich import esc

    return esc(text)


def _quote(text: str) -> str:
    return "\n".join(f"> {_esc(line)}" if line.strip() else ">" for line in text.splitlines()) or "> …"


def admin_card(student: User, text: str, at: datetime) -> str:
    from app.bot.rich import tg_time

    who = f"**{_esc(student.first_name or '—')}**"
    if student.username:
        who += f" · @{_esc(student.username)}"
    return (
        f"### 💬 Yangi murojaat\n"
        f"{who} · `{student.id}` · {student.lang.upper()} · {tg_time(at, 'r', at.strftime('%H:%M'))}\n\n"
        f"{_quote(text)}"
    )


def student_card(text: str, lang: str) -> str:
    return f"### 👨‍💼 Admin\n\n{_quote(text)}\n\n<sub>{t('support_reply_hint', lang)}</sub>"


def admin_kb(student_id: int) -> InlineKeyboardMarkup:
    from app.bot.keyboards import app_enabled, app_url

    row = [InlineKeyboardButton(text="↩️ Javob berish", callback_data=f"sup:reply:{student_id}", style="primary")]
    if app_enabled():
        row.append(InlineKeyboardButton(text="📂 Yozishma",
                                        web_app=WebAppInfo(url=app_url("admin") + f"?p=chat-{student_id}")))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def student_kb(lang: str) -> InlineKeyboardMarkup:
    from app.bot.keyboards import app_enabled, app_url

    row = [InlineKeyboardButton(text=t("support_btn_answer", lang), callback_data="sup:open", style="primary")]
    if app_enabled():
        row.append(InlineKeyboardButton(text=t("support_btn_app", lang), web_app=WebAppInfo(url=app_url() + "?p=support")))
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def _send_rich(bot: Bot, chat_id: int, markdown: str, kb=None):
    try:
        return await bot(SendRichMessage(chat_id=chat_id, rich_message=InputRichMessage(markdown=markdown),
                                         reply_markup=kb))
    except TelegramBadRequest:
        from app.services.tg_html import markdown_to_tg

        return await bot.send_message(chat_id, markdown_to_tg(markdown), reply_markup=kb)


# ---------------------------------------------------------------- flows

async def from_student(bot: Bot, student: User, text: str) -> SupportMessage:
    """Store a student message and deliver it to every admin."""
    msg = await add(student.id, text, from_admin=False)
    card = admin_card(student, msg.text, msg.created_at)
    for admin_id in await users.admin_ids():
        if admin_id == student.id:
            continue
        try:
            sent = await _send_rich(bot, admin_id, card, admin_kb(student.id))
            mid = getattr(sent, "message_id", None)
            if mid:
                async with Session() as s:
                    s.add(SupportRelay(admin_id=admin_id, message_id=mid, user_id=student.id))
                    await s.commit()
        except Exception as e:  # noqa: BLE001  (one unreachable admin must not stop the others)
            log.info("admin %s unreachable: %s", admin_id, e)
    return msg


async def from_admin(bot: Bot, admin: User, student_id: int, text: str) -> SupportMessage:
    """Store an admin answer and deliver it to the student (raises if the student blocked the bot)."""
    msg = await add(student_id, text, from_admin=True, admin_id=admin.id)
    student = await users.get(student_id)
    lang = student.lang if student else "uz"
    try:
        await _send_rich(bot, student_id, student_card(msg.text, lang), student_kb(lang))
    except TelegramForbiddenError:
        log.info("student %s blocked the bot", student_id)
    except Exception:  # noqa: BLE001  (stored anyway: the student sees it in the Mini App)
        log.exception("could not deliver admin reply to %s", student_id)
    return msg


async def relay_target(admin_id: int, message_id: int) -> int | None:
    async with Session() as s:
        return (await s.execute(
            select(SupportRelay.user_id).where(SupportRelay.admin_id == admin_id, SupportRelay.message_id == message_id)
        )).scalar_one_or_none()
