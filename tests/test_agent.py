"""The assistant as an agent: tool calls, confirmations and scheduled tasks."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from tests.test_api import auth, client  # noqa: F401,I001  (first: it sets the test environment)
from app.config import get_settings
from app.db import Session
from app.models import Broadcast, PendingAction, Task, User
from app.services import agent, ai, profile, tasks


def sse(*parts) -> httpx.Response:
    payload = {"candidates": [{"content": {"role": "model", "parts": list(parts)}}]}
    return httpx.Response(200, text="data: " + json.dumps(payload) + "\n\n")


@pytest.fixture
def gemini(monkeypatch):
    """Scripted Gemini: each request gets the next response; requests are recorded."""
    script, sent = [], []

    def handler(request: httpx.Request):
        sent.append(json.loads(request.content))
        return script.pop(0)

    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(profile, "learn_later", lambda *a: None)  # no background memory calls
    monkeypatch.setattr(ai, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return script, sent


def local_in(minutes: int) -> str:
    return tasks.local_str(datetime.now(timezone.utc) + timedelta(minutes=minutes))


async def test_student_agent_schedules_a_reminder(client, gemini):  # noqa: F811
    script, sent = gemini
    when = local_in(24 * 60)
    call = {"functionCall": {"name": "schedule_task", "id": "c1",
                             "args": {"kind": "reminder", "text": "Esse topşiriş", "run_at": when, "repeat": "once"}},
            "thoughtSignature": "sig-1"}
    script += [sse(call), sse({"text": f"✅ Eslataman: **{when}**"})]

    r = await client.post("/api/ai", headers=auth(300), json={"message": "ertaga şu payt esse haqida eslat"})
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == f"✅ Eslataman: **{when}**" and r.json()["actions"] == []

    names = {d["name"] for d in sent[0]["tools"][0]["functionDeclarations"]}
    assert {"schedule_task", "mark_deadline", "message_admin"} <= names
    assert not names & {"broadcast", "set_user_status", "update_bot_settings"}  # students: no admin tools
    # the model's turn goes back verbatim (thought signature included), then the tool result
    second = sent[1]["contents"]
    assert second[-2] == {"role": "model", "parts": [call]}
    response = second[-1]["parts"][0]["functionResponse"]
    assert response["name"] == "schedule_task" and response["id"] == "c1" and response["response"]["ok"]

    async with Session() as s:
        t = (await s.execute(Task.__table__.select().where(Task.user_id == 300))).one()
    assert t.kind == "reminder" and t.text == "Esse topşiriş" and tasks.local_str(t.run_at) == when


async def test_tool_errors_reach_the_model(client, gemini):  # noqa: F811
    script, sent = gemini
    script += [sse({"functionCall": {"name": "schedule_task",
                                     "args": {"kind": "reminder", "text": "x", "run_at": "2020-01-01 09:00"}}}),
               sse({"text": "Bu vaqt ötib ketgan."})]
    r = await client.post("/api/ai", headers=auth(301), json={"message": "2020-yilda eslat"})
    assert r.json()["answer"] == "Bu vaqt ötib ketgan."
    assert "past" in sent[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]["error"]


async def test_admin_broadcast_waits_for_confirmation(client, gemini, monkeypatch):  # noqa: F811
    from app.services import broadcast as bc

    ran = []

    async def fake_run(bot, bid):
        ran.append(bid)

    monkeypatch.setattr(bc, "run", fake_run)
    script, sent = gemini
    script += [sse({"functionCall": {"name": "broadcast", "args": {"text": "**Diqqat!** Ertaga dars yöq.", "langs": ["uz"]}}}),
               sse({"text": "Tayyor — ✅ ni bosing."})]
    r = await client.post("/api/ai", headers=auth(1, "Boss"), json={"message": "hammaga ertaga dars yöq deb yoz"})
    body = r.json()
    assert body["answer"] == "Tayyor — ✅ ni bosing." and len(body["actions"]) == 1
    assert "Ertaga dars yöq" in body["actions"][0]["html"]
    assert sent[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]["status"] == "awaiting_confirmation"
    async with Session() as s:
        assert (await s.execute(Broadcast.__table__.select())).first() is None  # nothing sent yet

    aid = body["actions"][0]["id"]
    assert (await client.post(f"/api/ai/actions/{aid}", headers=auth(2), json={"approve": True})).status_code == 404
    r = await client.post(f"/api/ai/actions/{aid}", headers=auth(1, "Boss"), json={"approve": True})
    assert r.json() == {"status": "done", "error": None}
    async with Session() as s:
        b = (await s.execute(Broadcast.__table__.select())).one()
    assert "<b>Diqqat!</b>" in b.html and b.segment == {"langs": ["uz"], "linked": None}
    # a second tap can't send it twice
    assert (await client.post(f"/api/ai/actions/{aid}", headers=auth(1, "Boss"), json={"approve": True})).json()["status"] == "done"
    assert len(ran) == 1


async def test_permissions_and_scheduled_runs(client):  # noqa: F811
    await client.get("/api/me", headers=auth(302))
    await client.get("/api/me", headers=auth(1, "Boss"))
    async with Session() as s:
        student, admin = await s.get(User, 302), await s.get(User, 1)
    r = await agent.call(agent.Ctx(user=student), "broadcast", {"text": "hi"})
    assert "not available" in r["error"]
    r = await agent.call(agent.Ctx(user=admin, scheduled=True), "kb_add", {"title": "a", "content": "b"})
    assert "not available" in r["error"]  # scheduled runs are read-only
    assert "error" not in await agent.call(agent.Ctx(user=admin, scheduled=True), "bot_stats", {})
    # every read-only tool answers with plain JSON (it goes straight back to Gemini)
    for name, t in agent.TOOLS.items():
        if t.readonly and not t.required:
            json.dumps(await agent.call(agent.Ctx(user=admin), name, {}))
    names = {d["name"] for d in agent.declarations(admin, scheduled=True)}
    assert "list_deadlines" in names and "schedule_task" not in names and "broadcast" not in names


class FakeBot:
    def __init__(self):
        self.sent = []

    async def __call__(self, method, request_timeout=None):
        self.sent.append(method)
        return True


async def test_due_tasks_run_and_repeat(client, monkeypatch):  # noqa: F811
    await client.get("/api/me", headers=auth(303))
    now = datetime.now(timezone.utc)
    async with Session() as s:
        s.add_all([
            Task(user_id=303, kind="reminder", text="Kitobni qaytariş", run_at=now - timedelta(seconds=30)),
            Task(user_id=303, kind="agent", text="bugungi deadlinelarim", run_at=now - timedelta(seconds=5), repeat="daily"),
            Task(user_id=303, kind="reminder", text="keyinroq", run_at=now + timedelta(hours=2)),
        ])
        await s.commit()

    async def fake_scheduled(user, instruction, bot):
        return f"Bugun 2 ta deadline ({instruction})"

    monkeypatch.setattr(ai, "run_scheduled", fake_scheduled)
    bot = FakeBot()
    await tasks.dispatch_due(bot)
    texts = [m.rich_message.markdown for m in bot.sent]
    assert any("Eslatma" in t and "> Kitobni qaytariş" in t for t in texts)
    assert any("Bugun 2 ta deadline (bugungi deadlinelarim)" in t for t in texts)
    assert not any("keyinroq" in t for t in texts)

    async with Session() as s:
        rows = {t.text: t for t in (await s.execute(Task.__table__.select())).all()}
    assert rows["Kitobni qaytariş"].active is False
    daily = rows["bugungi deadlinelarim"]
    assert daily.active and timedelta(hours=23) < daily.run_at.replace(tzinfo=timezone.utc) - now <= timedelta(days=1)
    bot.sent.clear()
    await tasks.dispatch_due(bot)  # nothing is due twice
    assert bot.sent == []


def test_next_run_weekdays_skips_weekend():
    friday = datetime(2026, 11, 13, 4, 0, tzinfo=timezone.utc)  # Fri 09:00 Tashkent
    nxt = tasks.next_run(friday, "weekdays", friday)
    assert nxt.astimezone(tasks.tz()).strftime("%a %H:%M") == "Mon 09:00"
    assert tasks.next_run(friday, "", friday) is None


async def test_bot_confirm_button(client, monkeypatch):  # noqa: F811
    """✅ under an agent action in Telegram runs it once and removes the buttons."""
    from aiogram import Bot, Dispatcher
    from aiogram.types import Update

    from app.bot.handlers import UserMiddleware, router

    calls = []

    async def fake_call(self, method, request_timeout=None):
        calls.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", fake_call)
    bot = Bot("123:TEST")
    dp = Dispatcher()
    dp.callback_query.outer_middleware(UserMiddleware())
    router._parent_router = None
    dp.include_router(router)
    await client.get("/api/me", headers=auth(1, "Boss"))
    async with Session() as s:
        row = PendingAction(user_id=1, tool="kb_delete", args={"doc_id": 999}, summary="🗑 #999")
        s.add(row)
        await s.commit()
    user = {"id": 1, "is_bot": False, "first_name": "Boss"}
    msg = {"message_id": 5, "date": 0, "chat": {"id": 1, "type": "private"}, "from": user}
    upd = {"update_id": 1, "callback_query": {"id": "1", "from": user, "chat_instance": "c",
                                              "data": f"act:ok:{row.id}", "message": msg}}
    await dp.feed_update(bot, Update.model_validate(upd, context={"bot": bot}))
    kinds = [type(c).__name__ for c in calls]
    assert "EditMessageReplyMarkup" in kinds
    assert any(type(c).__name__ == "SendRichMessage" and "Bajarildi" in c.rich_message.markdown for c in calls)
    async with Session() as s:
        assert (await s.get(PendingAction, row.id)).status == "done"
