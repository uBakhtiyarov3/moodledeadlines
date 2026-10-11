"""Telegram Rich Messages (Bot API 10.1+): send Markdown that Telegram renders with headings,
tables, lists, quotes and formulas, and stream AI answers as live drafts.

Every sender falls back to classic HTML messages if a rich call is rejected, so the bot keeps
working on chats/clients where rich messages aren't available.
"""

import logging
import random
import re
import time
from collections.abc import AsyncIterator
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.methods import SendRichMessage, SendRichMessageDraft
from aiogram.types import InputRichMessage

from app.services.tg_html import markdown_to_tg

log = logging.getLogger(__name__)

RICH_LIMIT = 32000  # Telegram allows 32768 UTF-8 chars per rich message
DRAFT_EVERY = 0.7  # seconds between streamed draft updates

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+\-.!|~=$])")


def esc(text: str) -> str:
    """Escape user/Moodle supplied text for Rich Markdown."""
    return _MD_SPECIAL.sub(r"\\\1", text or "")


def tg_time(dt: datetime, fmt: str = "wDT", fallback: str | None = None) -> str:
    """A date shown in each reader's own language/timezone (r = relative, wDT = weekday+date+time)."""
    label = fallback or dt.strftime("%d.%m %H:%M")
    return f"![{esc(label)}](tg://time?unix={int(dt.timestamp())}&format={fmt})"


async def _classic(bot: Bot, chat_id: int, markdown: str, reply_markup=None):
    """Fallback: convert to classic Telegram HTML, split to 4096-char messages."""
    from app.bot.handlers import split_message  # local import: avoid a cycle

    parts = split_message(markdown)
    for i, part in enumerate(parts):
        kb = reply_markup if i == len(parts) - 1 else None
        try:
            await bot.send_message(chat_id, markdown_to_tg(part), reply_markup=kb, disable_web_page_preview=True)
        except TelegramBadRequest:
            await bot.send_message(chat_id, part, reply_markup=kb, parse_mode=None, disable_web_page_preview=True)


async def send(bot: Bot, chat_id: int, markdown: str, reply_markup=None) -> None:
    """Send a rich message; fall back to classic HTML if Telegram rejects it."""
    if len(markdown) <= RICH_LIMIT:
        try:
            await bot(SendRichMessage(chat_id=chat_id, rich_message=InputRichMessage(markdown=markdown),
                                      reply_markup=reply_markup))
            return
        except TelegramForbiddenError:
            raise
        except TelegramBadRequest as e:
            log.warning("rich message rejected, using classic: %s", e.message[:200])
    await _classic(bot, chat_id, markdown, reply_markup)


async def stream(bot: Bot, chat_id: int, chunks: AsyncIterator[str], thinking: str = "…") -> str:
    """Show the answer growing live (rich draft), then persist it as a normal rich message.

    Returns the full text. Draft failures are ignored — the final message is what matters.
    """
    draft_id = random.randint(1, 2**31 - 1)
    drafts_ok = True

    async def draft(md: str):
        nonlocal drafts_ok
        if not drafts_ok:
            return
        try:
            await bot(SendRichMessageDraft(chat_id=chat_id, draft_id=draft_id,
                                           rich_message=InputRichMessage(markdown=md[:RICH_LIMIT])))
        except Exception as e:  # noqa: BLE001  (drafts are cosmetic)
            drafts_ok = False
            log.info("draft streaming disabled for this answer: %s", e)

    await draft(f"<tg-thinking>{thinking}</tg-thinking>")
    text, last = "", 0.0
    async for chunk in chunks:
        text += chunk
        if time.monotonic() - last >= DRAFT_EVERY and text.strip():
            last = time.monotonic()
            await draft(text)
    return text
