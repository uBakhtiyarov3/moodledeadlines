"""Scheduled work the assistant does for users: reminders, agent runs and scheduled broadcasts."""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import func, select

from app.config import get_settings
from app.db import Session
from app.models import Broadcast, Task, User, utcnow

log = logging.getLogger(__name__)

KINDS = ("reminder", "agent", "broadcast")
REPEATS = ("", "daily", "weekdays", "weekly")
MAX_ACTIVE = 30  # per user


class TaskError(ValueError):
    pass


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def parse_local(value: str) -> datetime:
    """'YYYY-MM-DD HH:MM' (Tashkent time) or ISO with offset → aware UTC datetime."""
    value = (value or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=tz()).astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as e:
        raise TaskError("bad_time: use 'YYYY-MM-DD HH:MM' in Tashkent time") from e
    return (dt if dt.tzinfo else dt.replace(tzinfo=tz())).astimezone(timezone.utc)


def next_run(prev: datetime, repeat: str, now: datetime) -> datetime | None:
    """The next occurrence after `now` for a repeating task (same local wall-clock time)."""
    if not repeat:
        return None
    local = prev.astimezone(tz())
    step = timedelta(weeks=1) if repeat == "weekly" else timedelta(days=1)
    while True:
        local = (local.replace(tzinfo=None) + step).replace(tzinfo=tz())
        if repeat == "weekdays" and local.weekday() >= 5:
            continue
        if local.astimezone(timezone.utc) > now:
            return local.astimezone(timezone.utc)


def local_str(dt: datetime) -> str:
    return dt.astimezone(tz()).strftime("%Y-%m-%d %H:%M")


def out(t: Task) -> dict:
    return {"id": t.id, "kind": t.kind, "text": t.text, "next_run": local_str(t.run_at),
            "repeat": t.repeat or "once", "active": t.active}


async def create(user_id: int, kind: str, text: str, run_at: str, repeat: str = "", payload: dict | None = None) -> Task:
    if kind not in KINDS:
        raise TaskError("kind must be reminder or agent")
    repeat = "" if repeat in (None, "none", "once") else repeat
    if repeat not in REPEATS:
        raise TaskError("repeat must be once, daily, weekdays or weekly")
    text = (text or "").strip()
    if not text:
        raise TaskError("empty text")
    when = parse_local(run_at)
    now = datetime.now(timezone.utc)
    if when < now - timedelta(minutes=1):
        raise TaskError(f"time is in the past (now is {local_str(now)} Tashkent)")
    async with Session() as s:
        active = (await s.execute(select(func.count(Task.id)).where(Task.user_id == user_id, Task.active.is_(True)))).scalar_one()
        if active >= MAX_ACTIVE:
            raise TaskError(f"too many active tasks ({MAX_ACTIVE}); cancel some first")
        t = Task(user_id=user_id, kind=kind, text=text[:4000], payload=payload or {}, run_at=max(when, now), repeat=repeat)
        s.add(t)
        await s.commit()
    return t


async def list_for(user_id: int) -> list[Task]:
    async with Session() as s:
        return (await s.execute(
            select(Task).where(Task.user_id == user_id, Task.active.is_(True)).order_by(Task.run_at)
        )).scalars().all()


async def cancel(user_id: int, task_id: int) -> bool:
    async with Session() as s:
        t = await s.get(Task, task_id)
        if not t or t.user_id != user_id or not t.active:
            return False
        t.active = False
        await s.commit()
    return True


# ---------------------------------------------------------------- dispatch (every minute)

async def _run_one(bot: Bot, t: Task) -> None:
    from app.bot import rich
    from app.i18n import t as tr
    from app.services import ai, broadcast

    async with Session() as s:
        user = await s.get(User, t.user_id)
    if user is None or user.is_banned:
        return
    if t.kind == "reminder":
        await rich.send(bot, user.id, f"### ⏰ {tr('task_reminder', user.lang)}\n\n> {rich.esc(t.text)}")
    elif t.kind == "agent":
        try:
            answer = await ai.run_scheduled(user, t.text, bot)
        except ai.AIUnavailable as e:
            answer = tr("task_failed", user.lang) + f" ({e.code})"
        await rich.send(bot, user.id, f"### 🤖 {tr('task_done', user.lang)}\n<sub>{rich.esc(t.text[:200])}</sub>\n\n{answer}")
    elif t.kind == "broadcast":
        p = t.payload or {}
        async with Session() as s:
            row = Broadcast(html=t.text, segment=p.get("segment") or {}, button_text=p.get("button_text"),
                            button_url=p.get("button_url"), created_by=user.id)
            s.add(row)
            await s.commit()
            bid = row.id
        await broadcast.run(bot, bid)
        await rich.send(bot, user.id, f"✅ {tr('task_broadcast_sent', user.lang)} #{bid}")


async def dispatch_due(bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    async with Session() as s:
        due = (await s.execute(
            select(Task).where(Task.active.is_(True), Task.run_at <= now).order_by(Task.run_at).limit(50)
        )).scalars().all()
        # claim them first so a slow run is never repeated by the next tick
        for t in due:
            t.last_run_at = utcnow()
            nxt = next_run(t.run_at, t.repeat, now)
            if nxt:
                t.run_at = nxt
            else:
                t.active = False
        await s.commit()
    for t in due:
        try:
            await _run_one(bot, t)
        except Exception:  # noqa: BLE001
            log.exception("task %s failed", t.id)
