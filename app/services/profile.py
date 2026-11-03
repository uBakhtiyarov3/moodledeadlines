"""Student profile and AI memory: what lets the assistant know who it is talking to."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.config import get_settings
from app.db import Session
from app.models import Deadline, Profile, User, utcnow
from app.services import users

log = logging.getLogger(__name__)

YEARS = ("1", "2", "3", "4", "master")
MAX_FACTS = 20
FACT_LEN = 160
EDITABLE = {"faculty": 160, "year": 16, "group_name": 64, "about": 600}

# The memory keeper runs on the lightest model after an answer, in the background.
MEMORY_PROMPT = """You keep a short memory about a university student for their study assistant (UWED Pulse).
You get the facts remembered so far and the latest exchange. Return the full updated list.

Keep only durable facts the student said about themselves that help future conversations:
their studies (faculty, major, year, group, courses, thesis topic), goals, learning preferences,
strengths and difficulties, languages, interests, plans, how they like to be addressed.
- Add a fact only if the student stated it (never infer from the assistant's words or from the question topic).
- Update or remove facts the student corrected or asked to forget.
- Never store: passwords, tokens, codes, phone numbers, addresses, documents, health, religion,
  political views, finances, or anything about other people.
- One short fact per item (max 15 words), in the language the student used, third person.
- At most 20 items; drop the least useful when full.

Reply with JSON only: {"facts": ["...", "..."]}"""

_tasks: set[asyncio.Task] = set()


def fact_list(raw) -> list[str]:
    out: list[str] = []
    for f in raw or []:
        f = " ".join(str(f).split())[:FACT_LEN]
        if f and f not in out:
            out.append(f)
    return out[:MAX_FACTS]


async def get(user_id: int) -> Profile:
    async with Session() as s:
        p = await s.get(Profile, user_id)
    return p or Profile(user_id=user_id, last_name="", moodle_name="", faculty="", year="", group_name="",
                        about="", memory=[], memory_on=True)


async def update(user_id: int, **fields) -> Profile:
    """Set any Profile columns (unknown keys ignored, text trimmed to the column limits)."""
    async with Session() as s:
        p = await s.get(Profile, user_id)
        if p is None:
            p = Profile(user_id=user_id, memory=[])
            s.add(p)
        for key, value in fields.items():
            if key in EDITABLE:
                value = (value or "").strip()[: EDITABLE[key]]
                if key == "year" and value not in YEARS:
                    value = ""
            elif key == "memory":
                value = fact_list(value)
            elif key not in ("last_name", "moodle_name", "memory_on"):
                continue
            setattr(p, key, value)
        p.updated_at = utcnow()
        await s.commit()
    return p


async def note_last_name(user_id: int, last_name: str | None) -> None:
    """Keep the Telegram last name current without a write on every update."""
    last_name = (last_name or "")[:128]
    async with Session() as s:
        p = await s.get(Profile, user_id)
        if (p.last_name if p else "") == last_name:
            return
    await update(user_id, last_name=last_name)


async def _courses(user_id: int) -> list[str]:
    since = datetime.now(timezone.utc) - timedelta(days=150)
    async with Session() as s:
        rows = await s.execute(
            select(Deadline.course, func.count(Deadline.id))
            .where(Deadline.user_id == user_id, Deadline.course != "", Deadline.due_at > since)
            .group_by(Deadline.course)
            .order_by(func.count(Deadline.id).desc())
            .limit(15)
        )
    return [c for c, _ in rows.all()]


async def context(u: User) -> str:
    """The <student_profile> block for the AI's system prompt."""
    p = await get(u.id)
    tz = ZoneInfo(get_settings().timezone)
    name = " ".join(filter(None, [u.first_name, p.last_name])) or "unknown"
    lines = []
    if users.is_admin(u):
        lines.append("- Role: BOT ADMINISTRATOR (verified by the server from their Telegram ID)")
    lines.append(f"- Name in Telegram: {name}" + (f" (@{u.username})" if u.username else ""))
    if p.moodle_name:
        lines.append(f"- Full name in Moodle: {p.moodle_name}")
    if p.faculty:
        lines.append(f"- Faculty / major: {p.faculty}")
    if p.year:
        lines.append(f"- Year of study: {'master’s programme' if p.year == 'master' else p.year}")
    if p.group_name:
        lines.append(f"- Group: {p.group_name}")
    if p.about:
        lines.append(f"- About themselves (written by the student): {p.about}")
    courses = await _courses(u.id)
    if courses:
        lines.append("- Moodle courses: " + "; ".join(courses))
    lines.append(f"- Moodle connected: {'yes' if u.ical_url_enc else 'no'}"
                 + (" · reminders paused" if u.paused else ""))
    lines.append(f"- Uses UWED Pulse since {u.created_at.astimezone(tz):%Y-%m-%d}")
    if p.memory_on and p.memory:
        lines.append("- Remembered from earlier chats:\n" + "\n".join(f"  - {f}" for f in p.memory))
    if users.is_admin(u):
        lines.append(await _bot_stats())
    return "\n".join(lines)


async def _bot_stats() -> str:
    """Live numbers an administrator may ask the assistant about."""
    from app.api.admin import stats

    st = await stats()
    return (
        f"- Bot right now: {st['users']} users, {st['linked']} with Moodle connected, "
        f"{st['active_week']} active in 7 days, {st['new_day']} new in 24 h, {st['blocked']} blocked the bot; "
        f"{st['ai_questions_day']} AI questions and {st['reminders_day']} reminders in 24 h; "
        f"{st['upcoming_deadlines']} upcoming deadlines tracked; {st['support_unread']} unread student chats"
    )


# ---------------------------------------------------------------- memory

async def _learn(user_id: int, question: str, answer: str) -> None:
    from app.services import ai

    p = await get(user_id)
    if not p.memory_on:
        return
    turn = (
        f"Remembered so far:\n{json.dumps(p.memory, ensure_ascii=False)}\n\n"
        f"Student: {question[:2000]}\n\nAssistant: {answer[:1500]}"
    )
    raw = await ai.quick_json(MEMORY_PROMPT, turn)
    if raw is None or not isinstance(raw.get("facts"), list):
        return
    facts = fact_list(raw["facts"])
    if facts != p.memory:
        await update(user_id, memory=facts)


def learn_later(user_id: int, question: str, answer: str) -> None:
    """Update the memory in the background so the student never waits for it."""
    if len((question or "").strip()) < 12:  # "ok", "rahmat", a bare file: nothing to learn
        return

    async def run():
        try:
            await _learn(user_id, question, answer)
        except Exception:  # noqa: BLE001
            log.exception("memory update failed for %s", user_id)

    task = asyncio.create_task(run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
