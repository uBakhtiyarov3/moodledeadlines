"""The assistant as an agent: tool calls, confirmations and scheduled tasks."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from tests.test_api import auth, client  # noqa: F401,I001  (first: it sets the test environment)
from app.config import get_settings
from app.db import Session
from app.models import Broadcast, PendingAction, Task, User
from app.services import agent, ai, profile, tasks, tgapi
from app.services import settings as rt


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
    monkeypatch.setitem(rt._cache, "agent_confirm", True)  # the admin turned confirmations on
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


async def test_admin_orders_run_straight_away(client, gemini, monkeypatch):  # noqa: F811
    """By default an admin's order is simply done — no confirmation step."""
    from app.services import broadcast as bc

    ran = []

    async def fake_run(bot, bid):
        ran.append(bid)

    monkeypatch.setattr(bc, "run", fake_run)
    script, _ = gemini
    script += [sse({"functionCall": {"name": "broadcast", "args": {"text": "Salom hammaga"}}}),
               sse({"text": "Yuborildi."})]
    r = await client.post("/api/ai", headers=auth(1, "Boss"), json={"message": "hammaga salom yoz"})
    assert r.json()["answer"] == "Yuborildi." and r.json()["actions"] == [] and len(ran) == 1


async def test_reply_buttons_in_mini_app(client, gemini):  # noqa: F811
    script, _ = gemini
    script += [sse({"functionCall": {"name": "reply_buttons", "args": {"buttons": [
                   {"text": "✅ Ha", "action": "say", "value": "Ha, tushundim", "style": "success"},
                   {"text": "Sayt", "action": "url", "value": "https://uwed.uz", "row": 1},
                   {"text": "bad", "action": "url", "value": "javascript:alert(1)"}]}}}),
               sse({"text": "Tushundingizmi?"})]
    r = await client.post("/api/ai", headers=auth(304), json={"message": "test"})
    assert r.json()["buttons"] == [
        {"text": "✅ Ha", "action": "say", "value": "Ha, tushundim", "style": "success", "row": 0},
        {"text": "Sayt", "action": "url", "value": "https://uwed.uz", "style": None, "row": 1}]


async def test_telegram_api_tool(client):  # noqa: F811
    from aiogram.methods import SendMessage, SetMyDescription

    await client.get("/api/me", headers=auth(1, "Boss"))
    await client.get("/api/me", headers=auth(305))
    async with Session() as s:
        admin, student = await s.get(User, 1), await s.get(User, 305)

    class Recorder(FakeBot):
        async def __call__(self, method, request_timeout=None):
            self.sent.append(method)
            if isinstance(method, SendMessage):
                from aiogram.types import Chat, Message

                return Message(message_id=7, date=datetime.now(timezone.utc), chat=Chat(id=method.chat_id, type="private"), text=method.text)
            return True

    bot = Recorder()
    ctx = agent.Ctx(user=admin, bot=bot)
    r = await agent.call(ctx, "telegram_api", {"method": "sendMessage", "params": json.dumps({
        "chat_id": 305, "text": "Salom", "reply_markup": {"inline_keyboard": [[{"text": "OK", "callback_data": "ok"}]]}})})
    assert r["ok"] and r["result"]["message_id"] == 7
    assert bot.sent[-1].reply_markup.inline_keyboard[0][0].callback_data == "ok"
    r = await agent.call(ctx, "telegram_api", {"method": "setmydescription", "params": {"description": "UWED Pulse"}})
    assert r["ok"] and isinstance(bot.sent[-1], SetMyDescription)
    assert "bad params" in (await agent.call(ctx, "telegram_api", {"method": "sendMessage", "params": "{}"}))["error"]
    assert "not allowed" in (await agent.call(ctx, "telegram_api", {"method": "logOut"}))["error"]
    assert "not valid JSON" in (await agent.call(ctx, "telegram_api", {"method": "getMe", "params": "{x"}))["error"]
    # students can't reach the Bot API
    assert "not available" in (await agent.call(agent.Ctx(user=student, bot=bot), "telegram_api", {"method": "getMe"}))["error"]

    ref = tgapi.reference("sendRichMessage")
    assert "rich_message: InputRichMessage" in ref["params"] and "markdown: str (optional)" in ref["types"]["InputRichMessage"]["fields"]
    assert any(m["method"] == "pinChatMessage" for m in tgapi.reference("pin")["matches"])
    assert "sendRichMessageDraft" in tgapi.names() and "logOut" not in tgapi.names()


@pytest.fixture
async def moodle_student(client, monkeypatch):  # noqa: F811
    """A student with the Moodle 'Pro' connection and a fake Moodle web service."""
    import io

    import docx

    from app.moodle import ws
    from app.security import encrypt

    await client.get("/api/me", headers=auth(310))
    async with Session() as s:
        u = await s.get(User, 310)
        u.ws_token_enc, u.moodle_userid = encrypt("tok"), 77
        await s.commit()

    d = docx.Document()
    d.add_paragraph("Mening essem: Markaziy Osiyoda suv muammosi.")
    buf = io.BytesIO()
    d.save(buf)
    grade = {"value": None}

    async def fake_call(token, function, **params):
        assert token == "tok"
        if function == "mod_assign_get_assignments":
            return {"courses": [{"fullname": "Xalqaro munosabatlar", "assignments": [
                {"id": 5, "cmid": 50, "name": "Esse: suv xavfsizligi", "duedate": 1_900_000_000, "grade": 100,
                 "intro": "<p>2000 söz. Dalillar va manbalar bilan.</p>",
                 "introattachments": [{"filename": "talablar.txt", "fileurl": "https://moodle.uwed.uz/f/talablar.txt", "mimetype": "text/plain"}]}]}]}
        if function == "core_grading_get_definitions":
            return {"areas": [{"definitions": [{"rubric": {"rubric_criteria": [
                {"description": "Argument", "levels": [{"score": 0, "definition": "Yöq"}, {"score": 10, "definition": "Kuçli"}]}]}}]}]}
        if function == "mod_assign_get_submission_status":
            return {"lastattempt": {"submission": {"status": "submitted", "timemodified": 1_890_000_000, "plugins": [
                {"type": "file", "fileareas": [{"files": [{"filename": "esse.docx", "fileurl": "https://moodle.uwed.uz/f/esse.docx", "mimetype": ""}]}]}]}}}
        if function == "core_enrol_get_users_courses":
            assert params["userid"] == 77
            return [{"id": 9, "fullname": "Xalqaro munosabatlar", "category": 331},  # 331 is inside 330
                    {"id": 10, "fullname": "Eski kurs (2021)", "category": 12}]
        if function == "core_course_get_categories":
            assert params["criteria[0][value]"] == 330 and params["addsubcategories"] == 1
            return [{"id": 330, "path": "/5/330"}, {"id": 331, "path": "/5/330/331"}]
        if function == "gradereport_user_get_grade_items":
            items = [{"id": 1, "itemtype": "course", "graderaw": 80}]
            if grade["value"]:
                items.append({"id": 3, "itemname": "Esse: suv xavfsizligi", "itemtype": "mod", "itemmodule": "assign", "cmid": 50,
                              "graderaw": 85, "gradeformatted": grade["value"], "grademax": 100, "feedback": "<p>Manbalar kam.</p>"})
            return {"usergrades": [{"gradeitems": items}]}
        raise AssertionError(function)

    async def fake_download(token, url, max_bytes=0):
        return {"https://moodle.uwed.uz/f/talablar.txt": "Mezon: argument, manbalar".encode(),
                "https://moodle.uwed.uz/f/esse.docx": buf.getvalue()}.get(url)

    monkeypatch.setattr(ws, "call", fake_call)
    monkeypatch.setattr(ws, "download", fake_download)
    async with Session() as s:
        yield await s.get(User, 310), grade


async def test_review_bundle_from_moodle(moodle_student):
    from app.services import coursework

    user, _ = moodle_student
    r = await agent.call(agent.Ctx(user=user), "moodle_assignments", {"query": "esse"})
    assert r["assignments"][0]["assignment_id"] == 5 and "_intro" not in r["assignments"][0]
    b = await coursework.review_bundle(user, 5)
    assert b["brief"] == "2000 söz. Dalillar va manbalar bilan."
    assert "Mezon: argument" in b["brief_files"][0]["text"]
    assert b["criteria"] == [{"criterion": "Argument", "levels": ["0: Yöq", "10: Kuçli"]}]
    assert b["submission_status"] == "submitted" and "suv muammosi" in b["submitted_files"][0]["text"]
    # not connected → a clear instruction instead of a crash
    r = await agent.call(agent.Ctx(user=User(id=12345)), "moodle_assignments", {})
    assert "Pro" in r["error"]


async def test_new_grade_notification(moodle_student):
    from app.services import coursework

    user, grade = moodle_student
    bot = FakeBot()
    assert await coursework.check_user(bot, user) == 0  # first look: just remembers
    grade["value"] = "85,00"
    assert await coursework.check_user(bot, user) == 1
    msg = bot.sent[-1].rich_message.markdown
    assert "Yangi baho" in msg and "Esse: suv xavfsizligi" in msg and "**85,00** / 100" in msg and "Manbalar kam\\." in msg
    buttons = bot.sent[-1].reply_markup.inline_keyboard[0]
    assert buttons[0].callback_data == "grade:9:3" and buttons[1].url.endswith("/mod/assign/view.php?id=50")
    assert await coursework.check_user(bot, user) == 0  # nothing new → silent


async def test_grades_page_and_hiding_courses(client, moodle_student):  # noqa: F811
    from app.models import Deadline

    user, grade = moodle_student
    h = auth(310)
    # not connected → the page asks to connect
    assert (await client.get("/api/grades", headers=auth(311))).json() == {"connected": False, "courses": [], "hidden": []}

    grade["value"] = "85,00"
    r = (await client.get("/api/grades?refresh=true", headers=h)).json()
    assert [c["id"] for c in r["courses"]] == [9]  # only category 330 and its subcategories
    course = r["courses"][0]
    assert course["fullname"] == "Xalqaro munosabatlar" and course["id"] == 9
    assert course["items"] == [{"name": "Esse: suv xavfsizligi", "grade": "85,00", "max": 100.0, "percent": 85,
                                "feedback": "Manbalar kam.", "graded_at": None,
                                "url": "https://moodle.uwed.uz/mod/assign/view.php?id=50"}]

    async with Session() as s:
        s.add(Deadline(user_id=310, uid="d1", title="Esse", course="Xalqaro munosabatlar",
                       due_at=datetime.now(timezone.utc) + timedelta(days=2)))
        await s.commit()
    assert len((await client.get("/api/deadlines", headers=h)).json()["items"]) == 1

    r = (await client.post("/api/grades/hidden", headers=h, json={"course_id": 9, "fullname": "Xalqaro munosabatlar", "shortname": "XM"})).json()
    assert r["courses"] == [] and r["hidden"] == [{"id": 9, "fullname": "Xalqaro munosabatlar"}]
    me = (await client.get("/api/me", headers=h)).json()
    assert set(me["muted_courses"]) == {"Xalqaro munosabatlar", "XM"}  # no reminders either
    assert (await client.get("/api/deadlines", headers=h)).json() == {"items": [], "courses": [], "course_names": {}}

    r = (await client.post("/api/grades/hidden", headers=h, json={"course_id": 9, "hidden": False})).json()
    assert r["hidden"] == [] and len(r["courses"]) == 1
    assert (await client.get("/api/me", headers=h)).json()["muted_courses"] == []



async def test_full_course_names_replace_calendar_codes(client):  # noqa: F811
    """The calendar only says 'xih_202627'; once Moodle told us the full name, everyone sees it."""
    from app.models import Deadline
    from app.services import coursenames, reminders

    await client.get("/api/me", headers=auth(320))
    async with Session() as s:
        d = Deadline(user_id=320, uid="m2", title="Midterm exam 2 is due", course="xih_202627",
                     due_at=datetime.now(timezone.utc) + timedelta(days=6))
        s.add(d)
        await s.commit()
    r = (await client.get("/api/deadlines", headers=auth(320))).json()
    assert r["items"][0]["course"] == "xih_202627"  # unknown yet → the code

    await coursenames.remember([{"shortname": "xih_202627", "fullname": "Xalqaro investitsiya huquqi / International Investment Law"}])
    r = (await client.get("/api/deadlines", headers=auth(320))).json()
    item = r["items"][0]
    assert item["course"] == "Xalqaro investitsiya huquqi / International Investment Law" and item["course_code"] == "xih_202627"
    assert r["courses"] == ["xih_202627"] and r["course_names"]["xih_202627"].startswith("Xalqaro investitsiya")
    assert "Xalqaro investitsiya huquqi" in reminders.format_reminder(d, 60, "uz", datetime.now(timezone.utc))

    await coursenames.load()  # survives a restart
    assert coursenames.full("xih_202627").startswith("Xalqaro investitsiya")


class FakeClaude:
    """Just enough of AsyncAnthropic.beta.messages.stream for the agent loop."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self.stream))

    def stream(self, **params):
        self.calls.append(params)
        reply = self.replies.pop(0)

        class Stream:
            async def __aenter__(s):
                async def gen():
                    for b in reply:
                        if b.type == "text":
                            yield b.text
                s.text_stream = gen()
                return s

            async def __aexit__(s, *a):
                return False

            async def get_final_message(s):
                return SimpleNamespace(content=reply, stop_reason="tool_use" if any(b.type == "tool_use" for b in reply) else "end_turn")

        return Stream()


from types import SimpleNamespace  # noqa: E402


async def test_claude_engine_for_admins(client, monkeypatch):  # noqa: F811
    from app.services import claude_agent

    tool_use = SimpleNamespace(type="tool_use", id="tu1", name="bot_stats", input={})
    fake = FakeClaude([[SimpleNamespace(type="text", text="Tekshiraman."), tool_use],
                       [SimpleNamespace(type="text", text="Botda 2 ta user bor.")]])
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")
    monkeypatch.setattr(claude_agent, "client", lambda: fake)
    monkeypatch.setattr(profile, "learn_later", lambda *a: None)
    monkeypatch.setitem(rt._cache, "ai_engine", "claude")
    await client.get("/api/me", headers=auth(331))

    r = await client.post("/api/ai", headers=auth(1, "Boss"), json={"message": "nechta user bor?"})
    assert r.json()["answer"] == "Tekshiraman.\n\nBotda 2 ta user bor."
    first, second = fake.calls
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert "query_database" in {t["name"] for t in first["tools"]}
    assert first["tools"][0]["input_schema"]["type"] == "object"
    result = second["messages"][-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "tu1" and '"users"' in result["content"]
    assert second["messages"][-2]["content"][1] is tool_use  # the assistant turn goes back unchanged

    async with Session() as s:
        admin, student = await s.get(User, 1), await s.get(User, 331)
    assert ai.engine_for(student) == "gemini"  # scope "admins"
    monkeypatch.setitem(rt._cache, "claude_scope", "everyone")
    assert ai.engine_for(student) == "claude"
    assert ai.engine_for(admin, [ai.Media("audio", "audio/ogg", b"x")]) == "gemini"  # voice stays on Gemini
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    assert ai.engine_for(admin) == "gemini"  # no key → Gemini


async def test_open_world_tools(client, gemini):  # noqa: F811
    from app.services import dbquery, webfetch

    await client.get("/api/me", headers=auth(332))
    r = await dbquery.run("SELECT id, lang FROM users WHERE id = 332")
    assert r["columns"] == ["id", "lang"] and r["rows"] == [[332, "uz"]]
    for bad in ("DELETE FROM users", "SELECT 1; DROP TABLE users", "UPDATE users SET lang='en'", "PRAGMA writable_schema=1"):
        assert "error" in await dbquery.run(bad), bad
    assert "error" in await dbquery.run("WITH x AS (SELECT 1) DELETE FROM users")
    assert (await client.patch("/api/me", headers=auth(332), json={"lang": "ru"})).json()["lang"] == "ru"  # writes still work

    for url in ("http://127.0.0.1:8000/", "http://169.254.169.254/computeMetadata/v1/", "file:///etc/passwd", "http://localhost/"):
        assert "error" in await webfetch.fetch(url), url
    assert webfetch.html_text("<html><head><title>x</title></head><body><script>bad()</script><h1>Salom</h1><p>dunyo &amp; biz</p></body>") == "Salom\ndunyo & biz"

    script, sent = gemini
    script.append(httpx.Response(200, json={"candidates": [{"content": {"parts": [
        {"executableCode": {"code": "print(2**10)"}}, {"codeExecutionResult": {"output": "1024\n"}}, {"text": "1024"}]},
        "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://example.org", "title": "Ex"}}]}}]}))
    r = await ai.gemini_builtin("2**10", "code_execution")
    assert r["answer"] == "1024" and r["output"] == ["1024\n"] and r["sources"][0]["url"] == "https://example.org"
    assert sent[-1]["tools"] == [{"code_execution": {}}]
