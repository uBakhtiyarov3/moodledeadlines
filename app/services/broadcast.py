"""Rate-limited broadcast of admin rich-text messages."""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendRichMessage
from aiogram.types import InputRichMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import Select, select

from app.db import Session
from app.models import Broadcast, User

log = logging.getLogger(__name__)


def segment_query(segment: dict) -> Select:
    q = select(User.id).where(User.is_banned.is_(False), User.blocked_bot.is_(False))
    langs = segment.get("langs") or []
    if langs:
        q = q.where(User.lang.in_(langs))
    linked = segment.get("linked")  # None = all, True = Moodle connected, False = not connected
    if linked is True:
        q = q.where(User.ical_url_enc.is_not(None))
    elif linked is False:
        q = q.where(User.ical_url_enc.is_(None))
    return q


def markup(button_text: str | None, button_url: str | None) -> InlineKeyboardMarkup | None:
    if button_text and button_url:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button_text, url=button_url, style="primary")]])
    return None


async def send_one(bot: Bot, chat_id: int, html: str, kb) -> bool:
    for _ in range(3):
        try:
            try:  # rich message (Bot API 10.x); classic HTML if this chat/client can't take it
                await bot(SendRichMessage(chat_id=chat_id, rich_message=InputRichMessage(html=html), reply_markup=kb))
            except TelegramBadRequest:
                await bot.send_message(chat_id, html, reply_markup=kb, disable_web_page_preview=False)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            async with Session() as s:
                u = await s.get(User, chat_id)
                if u:
                    u.blocked_bot = True
                    await s.commit()
            return False
        except Exception:  # noqa: BLE001
            log.exception("broadcast send failed to %s", chat_id)
            return False
    return False


async def run(bot: Bot, broadcast_id: int) -> None:
    async with Session() as s:
        b = await s.get(Broadcast, broadcast_id)
        ids = (await s.execute(segment_query(b.segment or {}))).scalars().all()
        b.status, b.total = "running", len(ids)
        await s.commit()
        html, kb = b.html, markup(b.button_text, b.button_url)

    sent = failed = 0
    for i, chat_id in enumerate(ids, 1):
        if await send_one(bot, chat_id, html, kb):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)  # ~20 msg/s, under Telegram's 30/s global limit
        if i % 25 == 0 or i == len(ids):
            async with Session() as s:
                b = await s.get(Broadcast, broadcast_id)
                b.sent, b.failed = sent, failed
                await s.commit()

    async with Session() as s:
        b = await s.get(Broadcast, broadcast_id)
        b.sent, b.failed, b.status = sent, failed, "done"
        await s.commit()
