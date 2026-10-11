"""Runtime settings editable from the admin panel (stored in DB, cached in memory)."""

from app.db import Session
from app.models import DEFAULT_OFFSETS, Setting

DEFAULT_SYSTEM_PROMPT = (
    "You are the official AI assistant of the University of World Economy and Diplomacy (UWED, uwed.uz) "
    "inside its student Telegram bot. Help students with questions about the university, studies, "
    "Moodle and their deadlines. Be friendly, concise and accurate. Reply in the student's language "
    "(Uzbek, Russian or English). Rely on the knowledge base excerpts provided; if the answer isn't "
    "there and you are not sure, say so and suggest contacting the dean's office or checking uwed.uz. "
    "Never invent dates, fees, phone numbers or rules. Format with short paragraphs and lists; "
    "you may use **bold** and *italic*."
)

DEFAULTS: dict = {
    "ai_enabled": True,
    "ai_daily_limit": 30,
    "ai_system_prompt": DEFAULT_SYSTEM_PROMPT,
    "maintenance": False,
    "default_offsets": DEFAULT_OFFSETS,
    "allowed_offsets": [4320, 2880, 1440, 720, 360, 180, 120, 60, 30],
}

_cache: dict = {}


async def load() -> None:
    from sqlalchemy import select

    async with Session() as s:
        rows = (await s.execute(select(Setting))).scalars().all()
    _cache.clear()
    _cache.update({r.key: r.value for r in rows})


def get(key: str):
    return _cache.get(key, DEFAULTS.get(key))


def all_settings() -> dict:
    return {k: get(k) for k in DEFAULTS}


async def set_many(values: dict) -> None:
    async with Session() as s:
        for k, v in values.items():
            if k not in DEFAULTS:
                continue
            await s.merge(Setting(key=k, value=v))
            _cache[k] = v
        await s.commit()
