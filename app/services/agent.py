"""The assistant's tools: what UWED Pulse can actually *do* for a student or an admin.

Each tool is a Gemini function declaration plus a handler. Handlers reuse the same code paths as
the Mini App API, so the agent can do exactly what the person could do by hand — no more.
High-impact admin actions (broadcast, bans, deleting knowledge, switching the bot off) are not run
right away: they become a PendingAction and the person confirms them with a button.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from fastapi import HTTPException
from app.db import Session
from app.models import PendingAction, User
from app.services import kb, profile, tasks, users
from app.services import settings as rt

log = logging.getLogger(__name__)

CONFIRM_TTL = timedelta(hours=1)


@dataclass
class Ctx:
    user: User
    bot: Bot | None = None
    scheduled: bool = False  # running a scheduled task: read-only tools only
    pending: list[dict] = field(default_factory=list)  # actions shown with ✅/❌ buttons
    buttons: list[dict] = field(default_factory=list)  # inline buttons for the reply (reply_buttons)
    done: list[str] = field(default_factory=list)  # tool names that ran
    tainted: bool = False  # outside text (web pages, students' messages) has entered this turn


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., Awaitable[dict]]
    params: dict = field(default_factory=dict)  # JSON-schema properties
    required: tuple = ()
    admin: bool = False
    readonly: bool = False  # also allowed in scheduled runs
    confirm: Callable[[dict], str | None] | None = None  # → summary when a ✅ is needed
    # → summary for a ✅ only when outside text has entered the turn (a web page or a student's message
    # could carry instructions aimed at the agent); otherwise the admin's order just runs
    guard: Callable[[dict], str] | None = None
    taints: bool = False  # its result is outside text

    def declaration(self) -> dict:
        d = {"name": self.name, "description": self.description}
        if self.params:
            d["parameters"] = {"type": "object", "properties": self.params}
            if self.required:
                d["parameters"]["required"] = list(self.required)
        return d


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, params: dict | None = None, required=(), **kw):
    def wrap(fn):
        TOOLS[name] = Tool(name, description, fn, params or {}, tuple(required), **kw)
        return fn

    return wrap


def S(desc: str, **kw) -> dict:
    return {"type": "string", "description": desc, **kw}


def I(desc: str) -> dict:
    return {"type": "integer", "description": desc}


def B(desc: str) -> dict:
    return {"type": "boolean", "description": desc}


def declarations(user: User, scheduled: bool = False) -> list[dict]:
    admin = users.is_admin(user)
    return [
        t.declaration() for t in TOOLS.values()
        if (admin or not t.admin) and (not scheduled or t.readonly)
    ]


async def call(ctx: Ctx, name: str, args: dict) -> dict:
    t = TOOLS.get(name)
    if t is None or (t.admin and not users.is_admin(ctx.user)) or (ctx.scheduled and not t.readonly):
        return {"error": f"tool {name} is not available here"}
    args = dict(args or {})
    summary = t.confirm(args) if t.confirm and rt.get("agent_confirm") else None
    if not summary and t.guard and ctx.tainted:
        summary = t.guard(args)
    if summary:
        async with Session() as s:
            row = PendingAction(user_id=ctx.user.id, tool=name, args=args, summary=summary)
            s.add(row)
            await s.commit()
        ctx.pending.append({"id": row.id, "summary": summary})
        return {"status": "awaiting_confirmation",
                "note": "Confirmation buttons are shown under your reply; the action runs only after ✅."}
    return await _run(ctx, t, args)


async def _run(ctx: Ctx, t: Tool, args: dict) -> dict:
    try:
        result = await t.handler(ctx, **args)
        ctx.done.append(t.name)
        ctx.tainted = ctx.tainted or t.taints
        return result
    except TypeError as e:  # wrong / missing arguments from the model
        return {"error": f"bad arguments: {e}"}
    except HTTPException as e:
        return {"error": str(e.detail)}
    except (tasks.TaskError, ValueError) as e:
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001
        log.exception("tool %s failed", t.name)
        return {"error": f"failed: {type(e).__name__}"}


async def resolve(user: User, action_id: int, approve: bool, bot: Bot | None) -> tuple[str, dict]:
    """Run or cancel a pending action. Returns (status, result)."""
    async with Session() as s:
        row = await s.get(PendingAction, action_id)
        if not row or row.user_id != user.id:
            return "missing", {}
        if row.status != "pending":
            return row.status, {}
        if datetime.now(timezone.utc) - row.created_at > CONFIRM_TTL:
            row.status = "expired"
            await s.commit()
            return "expired", {}
        row.status = "running" if approve else "cancelled"
        await s.commit()
    if not approve:
        return "cancelled", {}
    result = await _run(Ctx(user=user, bot=bot), TOOLS[row.tool], row.args)
    async with Session() as s:
        r = await s.get(PendingAction, action_id)
        r.status = "failed" if "error" in result else "done"
        await s.commit()
    return r.status, result


# ================================================================ student tools

@tool("list_deadlines", "The student's Moodle deadlines.",
      {"scope": S("upcoming (default) | done | past", enum=["upcoming", "done", "past"])}, readonly=True)
async def list_deadlines(ctx: Ctx, scope: str = "upcoming"):
    from app.api.student import deadlines

    r = await deadlines(scope=scope, user=ctx.user)
    items = [{"id": d["id"], "title": d["title"], "course": d["course"],
              "due": tasks.local_str(datetime.fromisoformat(d["due_at"])), "done": d["completed"]} for d in r["items"][:30]]
    return {"deadlines": items, "courses": r["courses"], "moodle_connected": bool(ctx.user.ical_url_enc)}


@tool("mark_deadline", "Mark a deadline as done (stops its reminders) or not done.",
      {"deadline_id": I("id from list_deadlines"), "done": B("true = done")}, required=("deadline_id",))
async def mark_deadline(ctx: Ctx, deadline_id: int, done: bool = True):
    from app.api.student import DoneIn, set_done

    d = await set_done(int(deadline_id), DoneIn(done=bool(done)), user=ctx.user)
    return {"ok": True, "title": d["title"], "done": d["completed"]}


@tool("sync_moodle", "Fetch the latest deadlines from Moodle now.")
async def sync_moodle(ctx: Ctx):
    from app.api.student import sync_now

    if not ctx.user.ical_url_enc:
        return {"error": "Moodle is not connected; the student connects it in the app (Settings → Moodle)."}
    r = await sync_now(user=ctx.user)
    return {"ok": True, "upcoming": r["count"]}


@tool("get_my_settings", "The student's reminder settings, language and muted courses.", readonly=True)
async def get_my_settings(ctx: Ctx):
    u = await users.get(ctx.user.id)
    return {"reminder_offsets_minutes": u.offsets, "allowed_offsets_minutes": rt.get("allowed_offsets"),
            "paused": u.paused, "muted_courses": u.muted_courses or [], "language": u.lang}


@tool("update_my_settings",
      "Change the student's deadline reminders or language. offsets are minutes before the deadline "
      "(only values from allowed_offsets_minutes; e.g. 1440 = 1 day, 60 = 1 hour). Pass only what changes.",
      {"reminder_offsets_minutes": {"type": "array", "items": {"type": "integer"}, "description": "full new list"},
       "paused": B("pause all deadline reminders"),
       "muted_courses": {"type": "array", "items": {"type": "string"}, "description": "full list of courses with no reminders"},
       "language": S("uz | ru | en", enum=["uz", "ru", "en"])})
async def update_my_settings(ctx: Ctx, reminder_offsets_minutes=None, paused=None, muted_courses=None, language=None):
    from app.api.student import Prefs, update_me

    offsets = [int(o) for o in reminder_offsets_minutes] if reminder_offsets_minutes is not None else None
    r = await update_me(Prefs(lang=language, offsets=offsets, paused=paused, muted_courses=muted_courses),
                        user=ctx.user)
    return {"ok": True, "reminder_offsets_minutes": r["offsets"], "paused": r["paused"],
            "muted_courses": r["muted_courses"], "language": r["lang"]}


@tool("update_my_profile", "Save the student's study details. Pass only what changes.",
      {"faculty": S("faculty or major"), "year": S("1 | 2 | 3 | 4 | master", enum=["1", "2", "3", "4", "master"]),
       "group_name": S("group"), "about": S("short self-description, goals")})
async def update_my_profile(ctx: Ctx, **fields):
    p = await profile.update(ctx.user.id, **{k: v for k, v in fields.items() if v is not None})
    return {"ok": True, "faculty": p.faculty, "year": p.year, "group_name": p.group_name, "about": p.about}


@tool("forget_memory", "Remove remembered facts about the student: those containing `text`, or all.",
      {"text": S("part of the fact to forget"), "all": B("forget everything")})
async def forget_memory(ctx: Ctx, text: str = "", all: bool = False):  # noqa: A002
    p = await profile.get(ctx.user.id)
    keep = [] if all else [f for f in p.memory or [] if not text or text.lower() not in f.lower()]
    await profile.update(ctx.user.id, memory=keep)
    return {"ok": True, "removed": len(p.memory or []) - len(keep), "left": len(keep)}


@tool("schedule_task",
      "Do something for the person later. kind=reminder sends `text` to them at run_at. kind=agent runs "
      "you at run_at with `text` as the instruction (e.g. 'list my deadlines for today') and sends them "
      "the answer (read-only tools only then). run_at is Tashkent time 'YYYY-MM-DD HH:MM'.",
      {"kind": S("reminder | agent", enum=["reminder", "agent"]), "text": S("reminder text or instruction"),
       "run_at": S("'YYYY-MM-DD HH:MM', Tashkent time"),
       "repeat": S("once | daily | weekdays | weekly", enum=["once", "daily", "weekdays", "weekly"])},
      required=("kind", "text", "run_at"))
async def schedule_task(ctx: Ctx, kind: str, text: str, run_at: str, repeat: str = "once"):
    if kind not in ("reminder", "agent"):
        return {"error": "kind must be reminder or agent"}
    t = await tasks.create(ctx.user.id, kind, text, run_at, repeat)
    return {"ok": True, **tasks.out(t)}


@tool("list_tasks", "The person's scheduled reminders and tasks.", readonly=True)
async def list_tasks(ctx: Ctx):
    return {"tasks": [tasks.out(t) for t in await tasks.list_for(ctx.user.id)]}


@tool("cancel_task", "Cancel a scheduled reminder or task.", {"task_id": I("id from list_tasks")}, required=("task_id",))
async def cancel_task(ctx: Ctx, task_id: int):
    return {"ok": await tasks.cancel(ctx.user.id, int(task_id))}


@tool("message_admin", "Send a message from the student to the bot's admins (the 'Chat with admin').",
      {"text": S("the message, in the student's words")}, required=("text",))
async def message_admin(ctx: Ctx, text: str):
    from app.services import support

    if not ctx.bot:
        return {"error": "messaging is unavailable right now"}
    await support.from_student(ctx.bot, ctx.user, text.strip()[:4000])
    return {"ok": True, "note": "Admins got it; their answer will arrive in this chat."}


@tool("search_knowledge", "Search UWED's knowledge base (rules, fees, contacts, schedules…).",
      {"query": S("what to look for")}, required=("query",), readonly=True)
async def search_knowledge(ctx: Ctx, query: str):
    return {"results": [{"doc": h.doc_title, "text": h.text} for h in kb.search(query)]}


# ================================================================ Moodle coursework (student's own account)

@tool("moodle_assignments",
      "The student's Moodle assignments (all courses) with ids, due dates and max grades. Needs the "
      "student's Moodle account connected (Pro).",
      {"query": S("optional part of the assignment or course name")}, readonly=True)
async def moodle_assignments(ctx: Ctx, query: str = ""):
    from app.services import coursework

    try:
        rows = await coursework.assignments(coursework.token_of(await users.get(ctx.user.id)))
    except coursework.NotConnected as e:
        return {"error": str(e)}
    q = (query or "").lower()
    rows = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows
            if not q or q in (r["name"] or "").lower() or q in (r["course"] or "").lower()]
    return {"assignments": rows[:60]}


@tool("get_assignment_for_review",
      "Open one Moodle assignment for review: the brief and its files, the grading criteria (rubric or "
      "marking guide when visible), the student's submitted files/text as text, and the teacher's grade "
      "and feedback if graded. Use it when the student wants their submission checked or a grade explained.",
      {"assignment_id": I("from moodle_assignments")}, required=("assignment_id",), readonly=True, taints=True)
async def get_assignment_for_review(ctx: Ctx, assignment_id: int):
    from app.services import coursework

    try:
        return await coursework.review_bundle(await users.get(ctx.user.id), int(assignment_id))
    except coursework.NotConnected as e:
        return {"error": str(e)}


@tool("check_new_grades", "Check Moodle right now for new grades or teacher feedback and notify the student.")
async def check_new_grades(ctx: Ctx):
    from app.services import coursework

    if not ctx.bot:
        return {"error": "not available here"}
    try:
        n = await coursework.check_user(ctx.bot, await users.get(ctx.user.id))
    except coursework.NotConnected as e:
        return {"error": str(e)}
    return {"ok": True, "new_notifications": n}


# ================================================================ the open world (everyone)

@tool("web_search",
      "Search the internet (Google) for current or outside information: news, facts, documentation, "
      "prices, events, anything not in the knowledge base. Returns an answer with sources.",
      {"query": S("what to find, as a full question")}, required=("query",), readonly=True, taints=True)
async def web_search(ctx: Ctx, query: str):
    from app.services import ai

    return await ai.gemini_builtin(f"Search the web and answer with the key facts and dates: {query}", "google_search")


@tool("fetch_url",
      "Open a public web page or file (http/https) and read its text: articles, PDFs, Word documents, "
      "JSON, plain text.",
      {"url": S("full http(s) URL")}, required=("url",), readonly=True, taints=True)
async def fetch_url(ctx: Ctx, url: str):
    from app.services import webfetch

    return await webfetch.fetch(url)


@tool("compute",
      "Run Python in a secure Google sandbox for exact calculations, statistics, data analysis, unit "
      "conversion, checking solutions. Describe the task and give all the data.",
      {"task": S("what to compute, with the data")}, required=("task",), readonly=True)
async def compute(ctx: Ctx, task: str):
    from app.services import ai

    return await ai.gemini_builtin(f"Write and run Python code to do this exactly, then state the result: {task}", "code_execution")


@tool("query_database",
      "Read-only SQL (SELECT/WITH) on the bot's own database for any statistics or lookup. Tables: users "
      "(id, first_name, username, lang, is_admin, is_banned, blocked_bot, created_at, last_seen_at, "
      "ai_used_today, paused, offsets, muted_courses, last_sync_at), deadlines (user_id, title, course, "
      "due_at, completed, hidden, gone), chat_messages (user_id, role, content, created_at), "
      "support_messages, broadcasts, knowledge_docs, profiles (user_id, faculty, year, group_name, about, "
      "memory), tasks, reminder_log, course_names, grades_seen, hidden_courses, settings. Max 200 rows.",
      {"sql": S("one SELECT or WITH statement")}, required=("sql",), admin=True, readonly=True)
async def query_database(ctx: Ctx, sql: str):
    from app.services import dbquery

    r = await dbquery.run(sql)
    # long text cells are people's own words (chats, profiles): treat them as outside text
    if any(isinstance(v, str) and len(v) > 60 for row in r.get("rows", []) for v in row):
        ctx.tainted = True
    return r


# ================================================================ Telegram UI (everyone)

APP_SECTIONS = ("deadlines", "ai", "support", "settings", "connect")


@tool("reply_buttons",
      "Put inline buttons under your reply in Telegram (use whenever choices or next steps make sense: "
      "quick answers, options, quiz answers, 'show more', links). action=say: tapping sends `value` (or the "
      "button text) to you as the person's next message; action=url: opens a https link; action=app: opens "
      "a section of the bot's Mini App (deadlines | ai | support | settings | connect). Buttons with the "
      "same row number share a row. Call once per reply, with all buttons.",
      {"buttons": {"type": "array", "description": "max 12", "items": {"type": "object", "properties": {
          "text": S("button label, short, may start with an emoji"),
          "action": S("say | url | app", enum=["say", "url", "app"]),
          "value": S("say: message to send (default = text); url: link; app: section"),
          "style": S("optional colour: primary | success | danger", enum=["primary", "success", "danger"]),
          "row": I("row number, from 0")}, "required": ["text", "action"]}}},
      required=("buttons",), readonly=True)
async def reply_buttons(ctx: Ctx, buttons: list):
    clean = []
    for b in (buttons or [])[:12]:
        text, action = str(b.get("text", "")).strip()[:64], b.get("action")
        value = str(b.get("value") or "").strip()
        if not text or action not in ("say", "url", "app"):
            continue
        if action == "url" and not value.startswith(("https://", "http://", "tg://")):
            continue
        if action == "app" and value not in APP_SECTIONS:
            value = "deadlines"
        clean.append({"text": text, "action": action, "value": value or text,
                      "style": b.get("style") if b.get("style") in ("primary", "success", "danger") else None,
                      "row": int(b.get("row") or 0)})
    ctx.buttons = clean
    return {"ok": True, "buttons": len(clean), "note": "They will appear under your reply."}


# ================================================================ admin tools

@tool("telegram_api",
      "Call ANY Telegram Bot API method as the bot (Bot API 10.3): send any kind of message (rich messages, "
      "photos by URL/file_id, polls, dice…) with inline keyboards to any chat or channel the bot can reach, "
      "edit/delete/pin/forward/copy messages, reactions, chat and member management where the bot is admin, "
      "invite links, forum topics, the bot's own name/description/commands/menu button, stars, gifts, "
      "stories… `method` is the API name (e.g. sendMessage, setMyDescription); `params` its JSON "
      "parameters. Look up exact params with telegram_api_reference first if unsure.",
      {"method": S("Bot API method name, e.g. sendRichMessage"),
       "params": S('the parameters as a JSON object, e.g. {"chat_id": 123, "text": "Hi"}')},
      required=("method",), admin=True)
async def telegram_api(ctx: Ctx, method: str, params: str | dict | None = None):
    import json

    from app.services import tgapi

    if not ctx.bot:
        return {"error": "the bot is not available here"}
    if params is None:
        params = {}
    if isinstance(params, str):  # Gemini can't declare a free-form object, so params come as JSON text
        try:
            params = json.loads(params or "{}")
        except ValueError as e:
            return {"error": f"params is not valid JSON: {e}"}
    if not isinstance(params, dict):
        return {"error": "params must be a JSON object"}
    return await tgapi.call(ctx.bot, method, params)


@tool("telegram_api_reference",
      "Exact parameters and types of a Bot API method (give its name), or methods matching a word "
      "(e.g. 'pin', 'topic', 'description').",
      {"query": S("method name or keyword")}, required=("query",), admin=True, readonly=True)
async def telegram_api_reference(ctx: Ctx, query: str):
    from app.services import tgapi

    return tgapi.reference(query)


@tool("bot_stats", "Live bot statistics.", admin=True, readonly=True)
async def bot_stats(ctx: Ctx):
    from app.api.admin import stats

    st = await stats()
    st.pop("growth", None)
    return st


@tool("find_users", "Find bot users by name, @username or Telegram ID.",
      {"query": S("name, username or id; empty = newest"),
       "filter": S("all | linked | banned | admins", enum=["all", "linked", "banned", "admins"]),
       "limit": I("max 50")}, admin=True, readonly=True)
async def find_users(ctx: Ctx, query: str = "", filter: str = "all", limit: int = 20):  # noqa: A002
    from app.api.admin import list_users

    return await list_users(q=query or "", filter=filter, offset=0, limit=max(1, min(int(limit), 50)))


@tool("user_info", "Everything about one user: settings, profile, upcoming deadlines.",
      {"user_id": I("Telegram ID")}, required=("user_id",), admin=True, readonly=True, taints=True)
async def user_info(ctx: Ctx, user_id: int):
    from app.api.admin import user_detail

    d = await user_detail(int(user_id))
    p = await profile.get(int(user_id))
    d["profile"] = {"last_name": p.last_name, "moodle_name": p.moodle_name, "faculty": p.faculty,
                    "year": p.year, "group": p.group_name, "about": p.about}
    return d


def _status_summary(a: dict) -> str | None:
    parts = []
    if a.get("banned") is not None:
        parts.append("🚫 bloklaş" if a["banned"] else "✅ blokdan çiqariş")
    if a.get("admin") is not None:
        parts.append("🛠 admin qiliş" if a["admin"] else "👤 adminlikdan oliş")
    return f"{' + '.join(parts) or 'özgariş'}: foydalanuvçi `{a.get('user_id')}`"


@tool("set_user_status", "Ban/unban a user or give/take admin rights.",
      {"user_id": I("Telegram ID"), "banned": B("ban (true) or unban (false)"), "admin": B("make admin / remove admin")},
      required=("user_id",), admin=True, confirm=_status_summary)
async def set_user_status(ctx: Ctx, user_id: int, banned: bool | None = None, admin: bool | None = None):
    from app.api.admin import UserPatch, patch_user

    await patch_user(int(user_id), UserPatch(is_banned=banned, is_admin=admin), me=ctx.user)
    return {"ok": True}


def _html(markdown: str) -> str:
    from app.services.tg_html import markdown_to_tg

    return markdown_to_tg(markdown)


@tool("message_user", "Send a message from the admins to one user (Markdown).",
      {"user_id": I("Telegram ID"), "text": S("message (Markdown)"),
       "button_text": S("optional link button text"), "button_url": S("optional link button URL")},
      required=("user_id", "text"), admin=True)
async def message_user(ctx: Ctx, user_id: int, text: str, button_text: str | None = None, button_url: str | None = None):
    from app.api.admin import MessageIn
    from app.api.admin import message_user as send

    await send(int(user_id), MessageIn(html=_html(text), button_text=button_text, button_url=button_url), b=ctx.bot)
    return {"ok": True}


def _broadcast_summary(a: dict) -> str:
    who = ", ".join(a.get("langs") or []) or "hamma"
    if a.get("only_moodle_linked"):
        who += " · faqat Moodle ulaganlar"
    when = f" · ⏰ {a['send_at']}" if a.get("send_at") else ""
    return f"📢 **Xabar yuboriş** ({who}{when}):\n\n" + "\n".join("> " + ln for ln in str(a.get("text", "")).splitlines()[:30])


@tool("broadcast",
      "Send an announcement (Markdown) to many users, now or at send_at. Segment by language and/or "
      "Moodle connection. Needs the admin's ✅.",
      {"text": S("the announcement, Telegram Markdown"),
       "langs": {"type": "array", "items": {"type": "string", "enum": ["uz", "ru", "en"]}, "description": "empty = everyone"},
       "only_moodle_linked": B("only users with Moodle connected"),
       "button_text": S("optional link button text"), "button_url": S("optional link button URL"),
       "send_at": S("optional 'YYYY-MM-DD HH:MM' Tashkent time; empty = now")},
      required=("text",), admin=True, confirm=_broadcast_summary)
async def broadcast(ctx: Ctx, text: str, langs=None, only_moodle_linked: bool = False,
                    button_text: str | None = None, button_url: str | None = None, send_at: str | None = None):
    from app.api.admin import BroadcastIn, Segment, _checked, start_broadcast

    seg = Segment(langs=list(langs or []), linked=True if only_moodle_linked else None)
    body = BroadcastIn(html=_html(text), button_text=button_text, button_url=button_url, segment=seg)
    if send_at:
        t = await tasks.create(ctx.user.id, "broadcast", _checked(body), send_at, payload={
            "segment": seg.model_dump(), "button_text": button_text, "button_url": button_url})
        return {"ok": True, "scheduled": tasks.out(t)}
    r = await start_broadcast(body, me=ctx.user, b=ctx.bot)
    return {"ok": True, "broadcast_id": r["id"]}


@tool("list_broadcasts", "Recent broadcasts and their delivery status.", admin=True, readonly=True)
async def list_broadcasts(ctx: Ctx):
    from app.api.admin import broadcasts

    return {"broadcasts": await broadcasts()}


@tool("read_ai_chats",
      "What students talk about with the AI assistant: their conversations (newest first), optionally for "
      "one student, only the last N days, or only messages containing a word. Use it to see topics, "
      "questions and problems, or one student's chat history.",
      {"user_id": I("only this student (Telegram ID)"), "search": S("only conversations with this word"),
       "days": I("how far back, default 7"), "limit": I("max messages, default 150, max 400")},
      admin=True, readonly=True, taints=True)
async def read_ai_chats(ctx: Ctx, user_id: int | None = None, search: str = "", days: int = 7, limit: int = 150):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models import ChatMessage

    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(int(days or 7), 365)))
    q = select(ChatMessage, User).join(User, User.id == ChatMessage.user_id).where(ChatMessage.created_at > since)
    if user_id:
        q = q.where(ChatMessage.user_id == int(user_id))
    if search:
        hits = select(ChatMessage.user_id).where(ChatMessage.content.ilike(f"%{search}%"), ChatMessage.created_at > since)
        q = q.where(ChatMessage.user_id.in_(hits))
    async with Session() as s:
        rows = (await s.execute(q.order_by(ChatMessage.id.desc()).limit(max(1, min(int(limit or 150), 400))))).all()
    chats: dict[int, dict] = {}
    for m, u in reversed(rows):
        c = chats.setdefault(u.id, {"user_id": u.id, "name": u.first_name, "username": u.username, "messages": []})
        c["messages"].append({"from": "student" if m.role == "user" else "ai", "at": tasks.local_str(m.created_at),
                              "text": m.content[:1500]})
    return {"conversations": list(chats.values()), "students": len(chats), "messages": len(rows)}


@tool("support_inbox", "Students' chats with the admins (newest first, with unread counts).", admin=True, readonly=True, taints=True)
async def support_inbox(ctx: Ctx):
    from app.services import support

    return {"threads": (await support.threads())[:30], "unread": await support.unread_total_for_admins()}


@tool("read_support_chat", "The whole admin chat with one student.",
      {"user_id": I("student's Telegram ID")}, required=("user_id",), admin=True, readonly=True, taints=True)
async def read_support_chat(ctx: Ctx, user_id: int):
    from app.services import support

    msgs = await support.thread(int(user_id))
    return {"messages": [{"from": "admin" if m.from_admin else "student", "text": m.text,
                          "at": tasks.local_str(m.created_at)} for m in msgs[-40:]]}


@tool("reply_support", "Answer a student in their admin chat.",
      {"user_id": I("student's Telegram ID"), "text": S("the reply")}, required=("user_id", "text"), admin=True)
async def reply_support(ctx: Ctx, user_id: int, text: str):
    from app.services import support

    if not await users.get(int(user_id)):
        return {"error": "no such user"}
    await support.from_admin(ctx.bot, ctx.user, int(user_id), text.strip()[:4000])
    return {"ok": True}


@tool("kb_list", "Knowledge-base documents (titles, ids, size).", admin=True, readonly=True)
async def kb_list(ctx: Ctx):
    from app.api.admin import kb_list as rows

    return {"docs": [{k: d[k] for k in ("id", "title", "enabled", "chars")} for d in await rows()]}


@tool("kb_get", "Read one knowledge-base document.", {"doc_id": I("id")}, required=("doc_id",), admin=True, readonly=True, taints=True)
async def kb_get(ctx: Ctx, doc_id: int):
    from app.api.admin import kb_list as rows

    for d in await rows():
        if d["id"] == int(doc_id):
            return {"id": d["id"], "title": d["title"], "enabled": d["enabled"], "content": d["content"][:12000]}
    return {"error": "not found"}


@tool("kb_add", "Add a document the AI will answer from (FAQ, rules, contacts…).",
      {"title": S("title"), "content": S("full text")}, required=("title", "content"), admin=True)
async def kb_add(ctx: Ctx, title: str, content: str):
    from app.api.admin import DocIn, kb_create

    return {"ok": True, **await kb_create(DocIn(title=title, content=content))}


@tool("kb_update", "Edit a knowledge-base document. Pass only what changes.",
      {"doc_id": I("id"), "title": S("new title"), "content": S("new full text"), "enabled": B("use it or not")},
      required=("doc_id",), admin=True)
async def kb_update(ctx: Ctx, doc_id: int, title: str | None = None, content: str | None = None, enabled: bool | None = None):
    from app.api.admin import DocIn
    from app.api.admin import kb_update as save

    cur = await kb_get(ctx, doc_id)
    if "error" in cur:
        return cur
    await save(int(doc_id), DocIn(title=title or cur["title"], content=content or cur["content"],
                                  enabled=cur["enabled"] if enabled is None else enabled))
    return {"ok": True}


@tool("kb_delete", "Delete a knowledge-base document.", {"doc_id": I("id")}, required=("doc_id",), admin=True,
      confirm=lambda a: f"🗑 Bilim bazasidan hujjatni öçiriş: #{a.get('doc_id')}")
async def kb_delete(ctx: Ctx, doc_id: int):
    from app.api.admin import kb_delete as delete

    await delete(int(doc_id))
    return {"ok": True}


@tool("get_bot_settings", "Bot-wide settings.", admin=True, readonly=True)
async def get_bot_settings(ctx: Ctx):
    return rt.all_settings()


def _settings_summary(a: dict) -> str | None:
    risky = []
    if a.get("maintenance") is True:
        risky.append("🛠 texnik işlar rejimini yoqiş (bot talabalar uçun töxtaydi)")
    if a.get("ai_enabled") is False:
        risky.append("🤖 AI'ni hamma uçun öçiriş")
    return "\n".join(risky) or None


@tool("update_bot_settings",
      "Change bot-wide settings. Pass only what changes. default_offsets are minutes (from allowed_offsets).",
      {"ai_enabled": B("AI on/off for everyone"), "tts_enabled": B("voice replies on/off"),
       "maintenance": B("maintenance mode: only admins can use the bot"),
       "ai_model": S("Gemini model id tried first, e.g. gemini-4-hydrogen, gemini-3.8-flash"),
       "grades_categories": {"type": "array", "items": {"type": "integer"},
                             "description": "Moodle category ids whose courses (with subcategories) the grades page shows; [] = all"},
       "agent_confirm": B("ask the admin for ✅ before broadcasts, bans, deletions, switching off"),
       "ai_daily_limit": I("AI questions per student per day"),
       "ai_system_prompt": S("extra instructions for the AI (admin notes), full new text"),
       "default_offsets": {"type": "array", "items": {"type": "integer"}, "description": "reminders for new students"}},
      admin=True, confirm=_settings_summary)
async def update_bot_settings(ctx: Ctx, **values):
    from app.api.admin import put_settings

    return {"ok": True, "settings": await put_settings({k: v for k, v in values.items() if v is not None})}


# ================================================================ full control of the server (admins)

def _shell_summary(a: dict) -> str:
    return "🖥 **Server buyrug\'i**\n```\n" + str(a.get("command", ""))[:1500] + "\n```"


@tool("run_shell",
      "Run any shell command inside the bot's server container (Linux, as the bot's user, working directory "
      "/srv = the app: app/, webapp/, data/bot.db, Python 3.13 with all packages). Use it for anything no "
      "other tool covers: inspect files and logs, run Python scripts (python -c / python - <<EOF), process "
      "data, export CSV files to data/, check the system. Changes to app files last "
      "only until the next update; permanent code changes go through the developer. Output is cut at 20 000 "
      "characters, timeout up to 300 s.",
      {"command": S("the shell command (sh)"), "timeout_seconds": I("default 60, max 300")},
      required=("command",), admin=True, guard=_shell_summary)
async def run_shell(ctx: Ctx, command: str, timeout_seconds: int = 60):
    from app.services import shell

    return await shell.run(command, int(timeout_seconds or 60))


def _sql_summary(a: dict) -> str:
    return "🗄 **Bazani özgartiriş** (avval zaxira nusxa olinadi)\n```sql\n" + str(a.get("sql", ""))[:1500] + "\n```"


@tool("execute_sql",
      "Change the bot's database with any SQL (UPDATE, INSERT, DELETE, CREATE …), several statements allowed. "
      "A backup copy of the database is saved first (data/backups/), so a mistake can be undone. Use "
      "query_database to look before you change.",
      {"sql": S("the SQL to run")}, required=("sql",), admin=True, guard=_sql_summary)
async def execute_sql(ctx: Ctx, sql: str):
    from app.services import dbquery

    return await dbquery.write(sql)
