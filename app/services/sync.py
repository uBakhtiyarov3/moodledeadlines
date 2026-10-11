"""Pull deadlines from Moodle into the database."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db import Session
from app.models import Deadline, User, utcnow
from app.moodle import ws
from app.moodle.ical import IcalUrlError, ParsedEvent, fetch_ical, parse_ical
from app.security import decrypt

log = logging.getLogger(__name__)


def merge_events(existing: dict[str, Deadline], events: list[ParsedEvent], user_id: int, now: datetime):
    """Upsert parsed events into `existing` (uid -> Deadline). Returns (new_rows, changed_count).

    Events that vanished from the feed while still in the future are flagged `gone`
    (the feed only covers ~60 days, so we never touch events beyond that window).
    """
    seen = set()
    new_rows: list[Deadline] = []
    changed = 0
    for e in events:
        seen.add(e.uid)
        d = existing.get(e.uid)
        if d is None:
            d = Deadline(
                user_id=user_id,
                uid=e.uid,
                moodle_event_id=e.moodle_event_id,
                title=e.title,
                course=e.course,
                description=e.description,
                url=e.url,
                due_at=e.due_at,
            )
            new_rows.append(d)
            continue
        if (d.title, d.course, d.due_at, d.url, d.gone) != (e.title, e.course, e.due_at, e.url, False):
            d.title, d.course, d.description, d.url = e.title, e.course, e.description, e.url
            d.due_at = e.due_at
            d.gone = False
            d.updated_at = now
            changed += 1
    window_end = now + timedelta(days=55)
    for uid, d in existing.items():
        if uid not in seen and now < d.due_at < window_end and not d.gone:
            d.gone = True
            changed += 1
    return new_rows, changed


async def sync_user(user_id: int, client: httpx.AsyncClient | None = None) -> int:
    """Sync one user. Returns number of upcoming deadlines. Raises IcalUrlError / httpx errors."""
    async with Session() as s:
        user = await s.get(User, user_id)
        if not user or not user.ical_url_enc:
            return 0
        url = decrypt(user.ical_url_enc)
        if not url:
            return 0
        now = utcnow()
        try:
            text = await fetch_ical(url, client)
            events = parse_ical(text)
        except (IcalUrlError, httpx.HTTPError) as exc:
            user.last_sync_error = str(exc)[:250] or exc.__class__.__name__
            await s.commit()
            raise
        rows = (await s.execute(select(Deadline).where(Deadline.user_id == user_id))).scalars().all()
        existing = {d.uid: d for d in rows}
        new_rows, _ = merge_events(existing, events, user_id, now)
        s.add_all(new_rows)

        # Option B: auto-detect completed items via the Moodle web service
        token = decrypt(user.ws_token_enc)
        if token:
            try:
                pending = await ws.pending_action_event_ids(token)
                for d in list(existing.values()):
                    if (
                        d.moodle_event_id
                        and d.due_at > now
                        and not d.completed
                        and d.moodle_event_id not in pending
                    ):
                        d.completed = True
                        d.completed_auto = True
                for d in existing.values():
                    # Teacher reopened / student's submission reverted
                    if d.completed_auto and d.moodle_event_id in pending:
                        d.completed = False
                        d.completed_auto = False
            except ws.MoodleAuthError as exc:
                if exc.code in ("invalidtoken", "accessexception"):
                    user.ws_token_enc = None
                log.warning("ws sync failed for %s: %s", user_id, exc.code)
            except httpx.HTTPError:
                log.warning("ws sync network error for %s", user_id)

        user.last_sync_at = now
        user.last_sync_error = None
        await s.commit()
        upcoming = [e for e in events if e.due_at > now]
        return len(upcoming)


async def sync_all() -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(minutes=settings.sync_interval_min)
    async with Session() as s:
        ids = (
            await s.execute(
                select(User.id).where(
                    User.ical_url_enc.is_not(None),
                    User.is_banned.is_(False),
                    User.blocked_bot.is_(False),
                    (User.last_sync_at.is_(None)) | (User.last_sync_at < stale_before),
                )
            )
        ).scalars().all()
    if not ids:
        return
    sem = asyncio.Semaphore(5)  # be gentle with moodle.uwed.uz
    async with httpx.AsyncClient(timeout=25) as client:

        async def one(uid: int):
            async with sem:
                try:
                    await sync_user(uid, client)
                except Exception as exc:  # noqa: BLE001
                    log.info("sync failed for %s: %s", uid, exc)

        await asyncio.gather(*(one(i) for i in ids))
    log.info("synced %d users", len(ids))
