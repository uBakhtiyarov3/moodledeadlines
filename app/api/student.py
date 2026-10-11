import base64
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.api.deps import current_user
from app.db import Session
from app.i18n import LANGS
from app.models import ChatMessage, Deadline, User
from app.moodle import ws
from app.moodle.ical import IcalUrlError
from app.services import ai, linking, users
from app.services import settings as rt
from app.services.sync import sync_user
from app.services.tg_html import markdown_to_tg

router = APIRouter(prefix="/api")


def user_out(u: User) -> dict:
    return {
        "id": u.id,
        "first_name": u.first_name,
        "lang": u.lang,
        "is_admin": users.is_admin(u),
        "linked": bool(u.ical_url_enc),
        "account_linked": bool(u.ws_token_enc),
        "last_sync_at": u.last_sync_at.isoformat() if u.last_sync_at else None,
        "last_sync_error": u.last_sync_error,
        "offsets": u.offsets,
        "paused": u.paused,
        "muted_courses": u.muted_courses or [],
        "allowed_offsets": rt.get("allowed_offsets"),
        "ai_enabled": bool(rt.get("ai_enabled")),
        "ai_left": max(0, int(rt.get("ai_daily_limit")) - (u.ai_used_today if u.ai_day == ai.today() else 0)),
    }


def deadline_out(d: Deadline) -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "course": d.course,
        "description": d.description[:600],
        "url": d.url,
        "due_at": d.due_at.isoformat(),
        "completed": d.completed,
        "completed_auto": d.completed_auto,
        "hidden": d.hidden,
    }


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return user_out(user)


class Prefs(BaseModel):
    lang: str | None = None
    offsets: list[int] | None = None
    paused: bool | None = None
    muted_courses: list[str] | None = None


@router.patch("/me")
async def update_me(p: Prefs, user: User = Depends(current_user)):
    async with Session() as s:
        u = await s.get(User, user.id)
        if p.lang in LANGS:
            u.lang = p.lang
        if p.offsets is not None:
            allowed = set(rt.get("allowed_offsets"))
            u.offsets = sorted({o for o in p.offsets if o in allowed}, reverse=True)
        if p.paused is not None:
            u.paused = p.paused
        if p.muted_courses is not None:
            u.muted_courses = [c[:255] for c in p.muted_courses][:100]
        await s.commit()
        return user_out(u)


@router.get("/deadlines")
async def deadlines(scope: str = "upcoming", user: User = Depends(current_user)):
    now = datetime.now(timezone.utc)
    q = select(Deadline).where(Deadline.user_id == user.id, Deadline.gone.is_(False))
    if scope == "upcoming":
        q = q.where(Deadline.due_at > now, Deadline.completed.is_(False), Deadline.hidden.is_(False)).order_by(Deadline.due_at)
    elif scope == "done":
        q = q.where(Deadline.completed.is_(True), Deadline.due_at > now - timedelta(days=30)).order_by(Deadline.due_at.desc())
    else:  # past
        q = q.where(Deadline.due_at <= now, Deadline.due_at > now - timedelta(days=30)).order_by(Deadline.due_at.desc())
    async with Session() as s:
        rows = (await s.execute(q.limit(100))).scalars().all()
        courses = sorted(
            {c for c in (await s.execute(select(Deadline.course).where(Deadline.user_id == user.id))).scalars() if c}
        )
    return {"items": [deadline_out(d) for d in rows], "courses": courses}


class DoneIn(BaseModel):
    done: bool = True


@router.post("/deadlines/{did}/done")
async def set_done(did: int, body: DoneIn, user: User = Depends(current_user)):
    async with Session() as s:
        d = await s.get(Deadline, did)
        if not d or d.user_id != user.id:
            raise HTTPException(404)
        d.completed, d.completed_auto = body.done, False
        await s.commit()
        return deadline_out(d)


class IcalIn(BaseModel):
    url: str = Field(max_length=1000)


@router.post("/moodle/ical")
async def link_ical(body: IcalIn, user: User = Depends(current_user)):
    try:
        n = await linking.link_ical(user.id, body.url)
    except IcalUrlError as e:
        raise HTTPException(400, e.args[0]) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, "network") from e
    return {"count": n, "user": user_out(await users.get(user.id))}


class AccountIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


@router.post("/moodle/account")
async def link_account(body: AccountIn, user: User = Depends(current_user)):
    try:
        await linking.link_account(user.id, body.username.strip(), body.password)
    except ws.MoodleAuthError as e:
        raise HTTPException(400, e.code) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, "network") from e
    return {"user": user_out(await users.get(user.id))}


@router.delete("/moodle")
async def unlink(account_only: bool = False, user: User = Depends(current_user)):
    await linking.unlink(user.id, keep_ical=account_only)
    return {"user": user_out(await users.get(user.id))}


@router.post("/moodle/sync")
async def sync_now(user: User = Depends(current_user)):
    try:
        n = await sync_user(user.id)
    except IcalUrlError as e:
        raise HTTPException(400, e.args[0]) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, "network") from e
    return {"count": n, "user": user_out(await users.get(user.id))}


class AskIn(BaseModel):
    message: str = Field(default="", max_length=4000)
    file_b64: str | None = Field(default=None, max_length=14_000_000)  # ~10 MB
    file_mime: str | None = None


FILE_KINDS = {"image/jpeg": "image", "image/png": "image", "image/webp": "image", "application/pdf": "document"}


@router.post("/ai")
async def ask(body: AskIn, user: User = Depends(current_user)):
    media = []
    if body.file_b64:
        kind = FILE_KINDS.get(body.file_mime or "")
        if not kind:
            raise HTTPException(400, "unsupported")
        try:
            media.append(ai.Media(kind, body.file_mime, base64.b64decode(body.file_b64, validate=True)))
        except ValueError as e:
            raise HTTPException(400, "bad_file") from e
    if not body.message.strip() and not media:
        raise HTTPException(400, "empty")
    try:
        answer = await ai.ask(user, body.message, media)
    except ai.AIUnavailable as e:
        raise HTTPException(429 if e.code in ("limit", "busy") else 503, e.code) from e
    return {"answer": answer, "html": markdown_to_tg(answer)}


@router.get("/ai/history")
async def history(user: User = Depends(current_user)):
    async with Session() as s:
        rows = (
            await s.execute(
                select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(40)
            )
        ).scalars().all()[::-1]
    return [
        {"role": m.role, "html": markdown_to_tg(m.content) if m.role == "assistant" else None, "text": m.content}
        for m in rows
    ]


@router.delete("/ai/history")
async def clear_history(user: User = Depends(current_user)):
    async with Session() as s:
        await s.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
        await s.commit()
    return {"ok": True}
