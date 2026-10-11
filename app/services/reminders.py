"""Reminder planning (pure) and dispatch."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.config import get_settings
from app.db import Session
from app.i18n import humanize_left, reminder_head, t
from app.models import Deadline, ReminderLog, User

log = logging.getLogger(__name__)

# How long after a threshold has passed we still consider it "on time"
# (covers scheduler hiccups / restarts). Older missed thresholds are skipped.
GRACE = timedelta(minutes=20)


@dataclass(frozen=True)
class Plan:
    send: int | None  # offset (minutes) to send now
    skip: tuple[int, ...]  # offsets to mark as skipped (passed / superseded)


def plan_reminder(due_at: datetime, now: datetime, offsets: list[int], already: set[int]) -> Plan:
    """Decide which reminder (if any) to send for one deadline right now.

    - A threshold `o` becomes due when `now >= due_at - o`.
    - Of all due-but-unsent thresholds only the *tightest* one is sent; larger ones are
      skipped, so a deadline discovered with 5h left yields one "6h" message, not five.
    - Nothing is sent once the deadline has passed.
    """
    if now >= due_at:
        return Plan(None, ())
    left = due_at - now
    reached = sorted(o for o in offsets if o not in already and left <= timedelta(minutes=o))
    if not reached:
        return Plan(None, ())
    tightest = reached[0]
    return Plan(tightest, tuple(reached[1:]))


def format_reminder(d: Deadline, offset: int, lang: str, now: datetime) -> str:
    """Rich Markdown reminder; the dates render in the student's own language and timezone."""
    from app.bot.rich import esc, tg_time

    tz = ZoneInfo(get_settings().timezone)
    local = d.due_at.astimezone(tz)
    left_min = int((d.due_at - now).total_seconds() // 60)
    head = reminder_head(offset, lang).replace("<b>", "**").replace("</b>", "**")
    parts = [f"### {head}", "", f"📘 **{esc(d.title)}**"]
    if d.course:
        parts.append(f"🎓 *{esc(d.course)}*")
    parts.append(
        f"🕒 {tg_time(d.due_at, 'wDT', f'{local:%d.%m.%Y %H:%M}')}  ·  "
        f"{t('left', lang)}: **{tg_time(d.due_at, 'r', humanize_left(left_min, lang))}**"
    )
    return "\n".join(parts)


async def dispatch_due_reminders(bot, now: datetime | None = None) -> int:
    """Send all reminders that are due now. Returns number of messages sent."""
    from aiogram.exceptions import TelegramForbiddenError
    from app.bot import rich
    from app.bot.keyboards import reminder_kb

    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(minutes=max(4320, 2880) + 1)
    sent = 0
    async with Session() as s:
        rows = (
            await s.execute(
                select(Deadline, User)
                .join(User, User.id == Deadline.user_id)
                .where(
                    Deadline.due_at > now,
                    Deadline.due_at <= horizon,
                    Deadline.completed.is_(False),
                    Deadline.hidden.is_(False),
                    Deadline.gone.is_(False),
                    User.paused.is_(False),
                    User.is_banned.is_(False),
                    User.blocked_bot.is_(False),
                )
            )
        ).all()
        for d, u in rows:
            if d.course and d.course in (u.muted_courses or []):
                continue
            logs = (
                await s.execute(
                    select(ReminderLog.offset_min).where(
                        ReminderLog.deadline_id == d.id, ReminderLog.due_at == d.due_at
                    )
                )
            ).scalars().all()
            plan = plan_reminder(d.due_at, now, list(u.offsets or []), set(logs))
            # Thresholds missed by more than GRACE (e.g. bot was down) are skipped silently
            if plan.send is not None and now - (d.due_at - timedelta(minutes=plan.send)) > GRACE:
                # still send it if it's the very first message for this deadline: a late
                # reminder beats none. Otherwise skip.
                if logs:
                    plan = type(plan)(None, plan.skip + (plan.send,))
            for o in plan.skip:
                s.add(ReminderLog(deadline_id=d.id, offset_min=o, due_at=d.due_at, skipped=True))
            if plan.send is not None:
                try:
                    await rich.send(bot, u.id, format_reminder(d, plan.send, u.lang, now), reminder_kb(d, u.lang))
                    sent += 1
                except TelegramForbiddenError:
                    u.blocked_bot = True
                except Exception:  # noqa: BLE001
                    log.exception("reminder send failed for user %s", u.id)
                    continue
                s.add(ReminderLog(deadline_id=d.id, offset_min=plan.send, due_at=d.due_at))
                await asyncio.sleep(0.04)  # stay well below Telegram's 30 msg/s
        await s.commit()
    return sent
