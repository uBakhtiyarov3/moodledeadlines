import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.deps import admin_user, bot
from app.api.student import user_out
from app.db import Session
from app.models import Broadcast, ChatMessage, Deadline, KnowledgeDoc, ReminderLog, User, utcnow
from app.services import ai, kb
from app.services import broadcast as bc
from app.services import settings as rt
from app.services.tg_html import markdown_to_tg, sanitize

router = APIRouter(prefix="/api/admin", dependencies=[Depends(admin_user)])
_tasks: set[asyncio.Task] = set()


@router.get("/stats")
async def stats():
    now = datetime.now(timezone.utc)
    day = now - timedelta(days=1)
    week = now - timedelta(days=7)
    async with Session() as s:
        async def count(q):
            return (await s.execute(q)).scalar_one()

        total = await count(select(func.count(User.id)))
        linked = await count(select(func.count(User.id)).where(User.ical_url_enc.is_not(None)))
        account = await count(select(func.count(User.id)).where(User.ws_token_enc.is_not(None)))
        active = await count(select(func.count(User.id)).where(User.last_seen_at > week))
        new_day = await count(select(func.count(User.id)).where(User.created_at > day))
        blocked = await count(select(func.count(User.id)).where(User.blocked_bot.is_(True)))
        upcoming = await count(
            select(func.count(Deadline.id)).where(Deadline.due_at > now, Deadline.completed.is_(False))
        )
        reminders_day = await count(
            select(func.count(ReminderLog.id)).where(ReminderLog.sent_at > day, ReminderLog.skipped.is_(False))
        )
        ai_day = await count(
            select(func.count(ChatMessage.id)).where(ChatMessage.created_at > day, ChatMessage.role == "user")
        )
        langs = dict((await s.execute(select(User.lang, func.count(User.id)).group_by(User.lang))).all())
        # new users per day for the last 14 days
        since = now - timedelta(days=14)
        created = (await s.execute(select(User.created_at).where(User.created_at > since))).scalars().all()
    series: dict[str, int] = {}
    for i in range(14, -1, -1):
        series[(now - timedelta(days=i)).strftime("%m-%d")] = 0
    for c in created:
        k = c.strftime("%m-%d")
        if k in series:
            series[k] += 1
    return {
        "users": total, "linked": linked, "account_linked": account, "active_week": active,
        "new_day": new_day, "blocked": blocked, "upcoming_deadlines": upcoming,
        "reminders_day": reminders_day, "ai_questions_day": ai_day, "langs": langs,
        "growth": [{"day": k, "n": v} for k, v in series.items()], "kb": kb.stats(),
    }


@router.get("/users")
async def list_users(q: str = "", filter: str = "all", offset: int = 0, limit: int = 30):
    query = select(User)
    if q:
        like = f"%{q.lstrip('@')}%"
        conds = [User.first_name.ilike(like), User.username.ilike(like)]
        if q.isdigit():
            conds.append(User.id == int(q))
        query = query.where(or_(*conds))
    if filter == "linked":
        query = query.where(User.ical_url_enc.is_not(None))
    elif filter == "banned":
        query = query.where(User.is_banned.is_(True))
    elif filter == "admins":
        query = query.where(User.is_admin.is_(True))
    async with Session() as s:
        total = (await s.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        rows = (await s.execute(query.order_by(User.created_at.desc()).offset(offset).limit(min(limit, 100)))).scalars().all()
    return {
        "total": total,
        "items": [
            {
                "id": u.id, "first_name": u.first_name, "username": u.username, "lang": u.lang,
                "linked": bool(u.ical_url_enc), "is_admin": u.is_admin, "is_banned": u.is_banned,
                "blocked_bot": u.blocked_bot, "created_at": u.created_at.isoformat(),
                "last_seen_at": u.last_seen_at.isoformat(),
            }
            for u in rows
        ],
    }


@router.get("/users/{uid}")
async def user_detail(uid: int):
    now = datetime.now(timezone.utc)
    async with Session() as s:
        u = await s.get(User, uid)
        if not u:
            raise HTTPException(404)
        upcoming = (
            await s.execute(
                select(Deadline).where(Deadline.user_id == uid, Deadline.due_at > now).order_by(Deadline.due_at).limit(20)
            )
        ).scalars().all()
    return {
        **user_out(u), "username": u.username, "is_banned": u.is_banned, "blocked_bot": u.blocked_bot,
        "created_at": u.created_at.isoformat(), "last_seen_at": u.last_seen_at.isoformat(),
        "deadlines": [{"title": d.title, "course": d.course, "due_at": d.due_at.isoformat(), "completed": d.completed} for d in upcoming],
    }


class UserPatch(BaseModel):
    is_banned: bool | None = None
    is_admin: bool | None = None


@router.patch("/users/{uid}")
async def patch_user(uid: int, p: UserPatch, me: User = Depends(admin_user)):
    if uid == me.id and (p.is_admin is False or p.is_banned):
        raise HTTPException(400, "cannot demote/ban yourself")
    async with Session() as s:
        u = await s.get(User, uid)
        if not u:
            raise HTTPException(404)
        if p.is_banned is not None:
            u.is_banned = p.is_banned
        if p.is_admin is not None:
            u.is_admin = p.is_admin
        await s.commit()
    return {"ok": True}


class MessageIn(BaseModel):
    html: str = Field(min_length=1, max_length=20000)
    button_text: str | None = Field(default=None, max_length=64)
    button_url: str | None = Field(default=None, max_length=512)


def _checked(body: MessageIn) -> str:
    text = sanitize(body.html)
    if not text:
        raise HTTPException(400, "empty")
    if len(text) > 4096:
        raise HTTPException(400, "too_long")
    if body.button_url and not body.button_url.startswith(("https://", "http://", "tg://")):
        raise HTTPException(400, "bad_button_url")
    return text


@router.post("/users/{uid}/message")
async def message_user(uid: int, body: MessageIn, b=Depends(bot)):
    ok = await bc.send_one(b, uid, _checked(body), bc.markup(body.button_text, body.button_url))
    if not ok:
        raise HTTPException(502, "send_failed")
    return {"ok": True}


@router.post("/broadcast/preview")
async def preview(body: MessageIn):
    text = sanitize(body.html)
    return {"html": text, "length": len(text)}


@router.post("/broadcast/test")
async def test_broadcast(body: MessageIn, me: User = Depends(admin_user), b=Depends(bot)):
    ok = await bc.send_one(b, me.id, _checked(body), bc.markup(body.button_text, body.button_url))
    return {"ok": ok}


class Segment(BaseModel):
    langs: list[str] = []
    linked: bool | None = None


class BroadcastIn(MessageIn):
    segment: Segment = Segment()


@router.post("/broadcast/count")
async def broadcast_count(seg: Segment):
    async with Session() as s:
        n = (await s.execute(select(func.count()).select_from(bc.segment_query(seg.model_dump()).subquery()))).scalar_one()
    return {"count": n}


@router.post("/broadcast")
async def start_broadcast(body: BroadcastIn, me: User = Depends(admin_user), b=Depends(bot)):
    text = _checked(body)
    async with Session() as s:
        row = Broadcast(
            html=text, segment=body.segment.model_dump(), button_text=body.button_text,
            button_url=body.button_url, created_by=me.id,
        )
        s.add(row)
        await s.commit()
        bid = row.id
    task = asyncio.create_task(bc.run(b, bid))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"id": bid}


@router.get("/broadcasts")
async def broadcasts():
    async with Session() as s:
        rows = (await s.execute(select(Broadcast).order_by(Broadcast.id.desc()).limit(20))).scalars().all()
    return [
        {"id": r.id, "html": r.html[:300], "status": r.status, "total": r.total, "sent": r.sent,
         "failed": r.failed, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


class DocIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=200_000)
    enabled: bool = True


@router.get("/kb")
async def kb_list():
    async with Session() as s:
        rows = (await s.execute(select(KnowledgeDoc).order_by(KnowledgeDoc.updated_at.desc()))).scalars().all()
    return [
        {"id": d.id, "title": d.title, "content": d.content, "enabled": d.enabled,
         "updated_at": d.updated_at.isoformat(), "chars": len(d.content)}
        for d in rows
    ]


@router.post("/kb")
async def kb_create(body: DocIn):
    async with Session() as s:
        d = KnowledgeDoc(**body.model_dump())
        s.add(d)
        await s.commit()
    await kb.rebuild()
    return {"id": d.id}


@router.put("/kb/{did}")
async def kb_update(did: int, body: DocIn):
    async with Session() as s:
        d = await s.get(KnowledgeDoc, did)
        if not d:
            raise HTTPException(404)
        d.title, d.content, d.enabled, d.updated_at = body.title, body.content, body.enabled, utcnow()
        await s.commit()
    await kb.rebuild()
    return {"ok": True}


@router.delete("/kb/{did}")
async def kb_delete(did: int):
    async with Session() as s:
        d = await s.get(KnowledgeDoc, did)
        if d:
            await s.delete(d)
            await s.commit()
    await kb.rebuild()
    return {"ok": True}


@router.get("/settings")
async def get_settings_():
    return rt.all_settings()


@router.put("/settings")
async def put_settings(values: dict):
    clean = {}
    if "ai_enabled" in values:
        clean["ai_enabled"] = bool(values["ai_enabled"])
    if "tts_enabled" in values:
        clean["tts_enabled"] = bool(values["tts_enabled"])
    if "maintenance" in values:
        clean["maintenance"] = bool(values["maintenance"])
    if "ai_daily_limit" in values:
        clean["ai_daily_limit"] = max(0, min(int(values["ai_daily_limit"]), 1000))
    if "ai_system_prompt" in values:
        clean["ai_system_prompt"] = str(values["ai_system_prompt"])[:20000]
    if "default_offsets" in values:
        allowed = set(rt.get("allowed_offsets"))
        clean["default_offsets"] = sorted({int(o) for o in values["default_offsets"] if int(o) in allowed}, reverse=True)
    await rt.set_many(clean)
    return rt.all_settings()


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.post("/ai/test")
async def ai_test(body: AskIn, me: User = Depends(admin_user)):
    hits = kb.search(body.message)
    try:
        answer = await ai.ask(me, body.message)
    except ai.AIUnavailable as e:
        raise HTTPException(503, e.code) from e
    return {
        "html": markdown_to_tg(answer),
        "sources": [{"title": h.doc_title, "excerpt": h.text[:200]} for h in hits],
    }
