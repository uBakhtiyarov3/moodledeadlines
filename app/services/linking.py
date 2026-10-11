"""Connect / disconnect a student's Moodle (shared by the bot and the Mini App API)."""

import httpx
from sqlalchemy import delete

from app.db import Session
from app.models import Deadline, User
from app.moodle import ws
from app.moodle.ical import fetch_ical, normalize_export_url, parse_ical, userid_from_url
from app.security import encrypt
from app.services.sync import sync_user


async def link_ical(user_id: int, raw_url: str) -> int:
    """Validate, test-fetch and store the export URL, then sync. Raises IcalUrlError/httpx.HTTPError."""
    url = normalize_export_url(raw_url)
    parse_ical(await fetch_ical(url))  # fail fast before saving
    async with Session() as s:
        u = await s.get(User, user_id)
        u.ical_url_enc = encrypt(url)
        u.moodle_userid = userid_from_url(url)
        u.last_sync_error = None
        await s.commit()
    return await sync_user(user_id)


async def link_account(user_id: int, username: str, password: str) -> int:
    """Option B: exchange credentials for a token (password is not stored)."""
    token = await ws.get_token(username, password)
    moodle_uid = await ws.site_userid(token)
    async with Session() as s:
        u = await s.get(User, user_id)
        u.ws_token_enc = encrypt(token)
        u.moodle_userid = u.moodle_userid or moodle_uid
        await s.commit()
    try:
        return await sync_user(user_id)
    except httpx.HTTPError:
        return 0


async def unlink(user_id: int, keep_ical: bool = False) -> None:
    async with Session() as s:
        u = await s.get(User, user_id)
        u.ws_token_enc = None
        if not keep_ical:
            u.ical_url_enc = None
            u.moodle_userid = None
            u.last_sync_at = None
            await s.execute(delete(Deadline).where(Deadline.user_id == user_id))
        await s.commit()
