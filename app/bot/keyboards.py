from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.config import get_settings
from app.i18n import t
from app.models import Deadline


def app_url(path: str = "app") -> str:
    return f"{get_settings().public_url.rstrip('/')}/{path}/"


def app_enabled() -> bool:
    """Telegram only opens Mini Apps over HTTPS; without it the bot runs chat-only."""
    return get_settings().public_url.startswith("https://")


def lang_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
            ]
        ]
    )


def main_kb(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        is_persistent=True,
        keyboard=[
            [
                KeyboardButton(text=t("btn_deadlines", lang)),
                KeyboardButton(text=t("btn_ai", lang)),
            ],
            [
                # Plain button on purpose: Mini Apps opened from a reply-keyboard button get
                # no initData from Telegram, so the app couldn't identify the user. The bot
                # answers it with an inline web_app button instead (which does carry initData).
                KeyboardButton(text=t("btn_settings", lang)),
                KeyboardButton(text=t("btn_lang", lang)),
            ],
        ],
    )


def open_app_kb(lang: str, section: str = "", text_key: str = "open_app") -> InlineKeyboardMarkup | None:
    if not app_enabled():
        return None
    url = app_url() + (f"#{section}" if section else "")
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t(text_key, lang), web_app=WebAppInfo(url=url))]]
    )


def admin_kb(lang: str) -> InlineKeyboardMarkup | None:
    if not app_enabled():
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=t("open_admin", lang), web_app=WebAppInfo(url=app_url("admin")))]]
    )


def reminder_kb(d: Deadline, lang: str) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=t("btn_done", lang), callback_data=f"done:{d.id}")]
    if d.url:
        row.append(InlineKeyboardButton(text=t("btn_open_moodle", lang), url=d.url))
    return InlineKeyboardMarkup(inline_keyboard=[row])
