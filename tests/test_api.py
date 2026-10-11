"""End-to-end API tests against an in-memory app (no Telegram, no Moodle, no Bedrock)."""

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlencode

os.environ.update(
    BOT_TOKEN="123:TEST",
    ADMIN_IDS="1",
    RUN_BOT="false",
    DATABASE_URL="sqlite+aiosqlite:///./data/test.db",
    SECRET_KEY="test",
)

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import Session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Deadline, ReminderLog  # noqa: E402
from app.moodle import ical as ical_mod  # noqa: E402
from app.services import ai as ai_mod  # noqa: E402
from app.services import linking  # noqa: E402
from app.services import reminders  # noqa: E402

ICS_FUTURE = lambda: f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:900@moodle.uwed.uz
SUMMARY:Essay due
DTSTART:{(datetime.now(timezone.utc) + timedelta(hours=5)).strftime('%Y%m%dT%H%M%SZ')}
CATEGORIES:Diplomacy 101
END:VEVENT
BEGIN:VEVENT
UID:901@moodle.uwed.uz
SUMMARY:Quiz closes
DTSTART:{(datetime.now(timezone.utc) + timedelta(days=10)).strftime('%Y%m%dT%H%M%SZ')}
CATEGORIES:Economics
END:VEVENT
END:VCALENDAR
"""


def auth(uid: int, name="Ali", lang="uz") -> dict:
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": uid, "first_name": name, "language_code": lang})}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", b"123:TEST", hashlib.sha256).digest()
    h = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return {"Authorization": "tma " + urlencode({**fields, "hash": h})}


@pytest.fixture
async def client(monkeypatch):
    from app.db import engine

    await engine.dispose()
    if os.path.exists("data/test.db"):
        os.remove("data/test.db")

    async def fake_fetch(url, client=None):
        return ICS_FUTURE()

    monkeypatch.setattr(ical_mod, "fetch_ical", fake_fetch)
    monkeypatch.setattr(linking, "fetch_ical", fake_fetch)
    import app.services.sync as sync_mod

    monkeypatch.setattr(sync_mod, "fetch_ical", fake_fetch)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            yield c


async def test_auth_required(client):
    assert (await client.get("/api/me")).status_code == 401
    bad = {"Authorization": "tma auth_date=1&hash=abc"}
    assert (await client.get("/api/me", headers=bad)).status_code == 401


async def test_student_flow(client):
    h = auth(42, lang="ru")
    me = (await client.get("/api/me", headers=h)).json()
    assert me["lang"] == "ru" and not me["linked"] and not me["is_admin"]

    r = await client.post("/api/moodle/ical", headers=h, json={"url": "https://evil.com/x"})
    assert r.status_code == 400 and r.json()["detail"] == "wrong_host"

    url = "https://moodle.uwed.uz/calendar/export_execute.php?userid=5&authtoken=" + "b" * 32
    r = await client.post("/api/moodle/ical", headers=h, json={"url": url})
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 2 and r.json()["user"]["linked"]

    items = (await client.get("/api/deadlines", headers=h)).json()
    assert [i["title"] for i in items["items"]] == ["Essay due", "Quiz closes"]
    assert items["courses"] == ["Diplomacy 101", "Economics"]

    r = await client.patch("/api/me", headers=h, json={"offsets": [1440, 60, 999], "paused": False, "lang": "en"})
    assert r.json()["offsets"] == [1440, 60] and r.json()["lang"] == "en"

    did = items["items"][1]["id"]
    assert (await client.post(f"/api/deadlines/{did}/done", headers=h, json={"done": True})).json()["completed"]
    done = (await client.get("/api/deadlines?scope=done", headers=h)).json()["items"]
    assert [d["id"] for d in done] == [did]

    # other users can't touch it
    assert (await client.post(f"/api/deadlines/{did}/done", headers=auth(43), json={"done": False})).status_code == 404


async def test_reminder_dispatch(client):
    h = auth(50)
    url = "https://moodle.uwed.uz/calendar/export_execute.php?userid=5&authtoken=" + "c" * 32
    await client.post("/api/moodle/ical", headers=h, json={"url": url})
    sent = []

    class FakeBot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    assert await reminders.dispatch_due_reminders(FakeBot()) == 1  # only the 6h one for the 5h-away essay
    assert "6" in sent[0][1] and "Essay due" in sent[0][1]
    assert await reminders.dispatch_due_reminders(FakeBot()) == 0  # not repeated
    async with Session() as s:
        from sqlalchemy import select

        logs = (await s.execute(select(ReminderLog))).scalars().all()
        assert sorted(l.offset_min for l in logs) == [360, 720, 1440, 4320]


async def test_admin_access_and_features(client, monkeypatch):
    assert (await client.get("/api/admin/stats", headers=auth(42))).status_code == 403
    ha = auth(1, "Boss")
    s = (await client.get("/api/admin/stats", headers=ha)).json()
    assert s["users"] >= 1

    # knowledge base + AI test with a fake Bedrock client
    r = await client.post("/api/admin/kb", headers=ha, json={"title": "Kutubxona", "content": "Kutubxona 9:00 dan 18:00 gacha ishlaydi."})
    assert r.status_code == 200

    sent = []

    def gemini(request: httpx.Request):
        sent.append(json.loads(request.content))
        assert request.headers["x-goog-api-key"] == "test-key"
        assert request.url.path.endswith("/models/gemini-flash-latest:generateContent")
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": "thinking...", "thought": True}, {"text": "**9:00–18:00**"}]}}]})

    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(ai_mod, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(gemini)))
    r = await client.post("/api/admin/ai/test", headers=ha, json={"message": "kutubxona qachon ishlaydi"})
    assert r.status_code == 200, r.text
    assert r.json()["html"] == "<b>9:00–18:00</b>"
    assert r.json()["sources"][0]["title"] == "Kutubxona"
    system = sent[0]["system_instruction"]["parts"][0]["text"]
    assert "UWED Pulse" in system and "<tutor_mode>" in system and "Kutubxona 9:00" in system
    assert sent[0]["contents"][-1] == {"role": "user", "parts": [{"text": "kutubxona qachon ishlaydi"}]}

    # image + PDF via the Mini App go out as inline_data parts
    png = base64.b64encode(b"\x89PNG fake").decode()
    r = await client.post("/api/ai", headers=ha, json={"message": "tekshir", "file_b64": png, "file_mime": "image/png"})
    assert r.status_code == 200, r.text
    parts = sent[-1]["contents"][-1]["parts"]
    assert parts[0]["inline_data"] == {"mime_type": "image/png", "data": png} and parts[1] == {"text": "tekshir"}
    # history keeps a label, not the bytes; previous turns become user/model roles
    assert [c["role"] for c in sent[-1]["contents"]] == ["user", "model", "user"]
    bad = await client.post("/api/ai", headers=ha, json={"message": "x", "file_b64": png, "file_mime": "video/mp4"})
    assert bad.status_code == 400

    # rate limited by Google → friendly "busy"
    monkeypatch.setattr(ai_mod, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429))))
    r = await client.post("/api/ai", headers=ha, json={"message": "salom"})
    assert r.status_code == 429 and r.json()["detail"] == "busy"
    monkeypatch.setattr(ai_mod, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(gemini)))

    # Bedrock provider still works when selected
    calls = {}

    class FakeMessages:
        async def create(self, **kw):
            calls.update(kw)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="ok")])

    monkeypatch.setattr(get_settings(), "ai_provider", "bedrock")
    monkeypatch.setattr(ai_mod, "client", lambda: SimpleNamespace(messages=FakeMessages()))
    r = await client.post("/api/admin/ai/test", headers=ha, json={"message": "salom"})
    assert r.json()["html"] == "ok" and calls["model"] == "us.anthropic.claude-opus-4-5-20251101-v1:0"
    monkeypatch.setattr(get_settings(), "ai_provider", "gemini")

    # student chat + history + limit
    await client.put("/api/admin/settings", headers=ha, json={"ai_daily_limit": 1})
    hs = auth(77)
    assert (await client.post("/api/ai", headers=hs, json={"message": "salom"})).status_code == 200
    assert (await client.post("/api/ai", headers=hs, json={"message": "yana"})).json()["detail"] == "limit"
    hist = (await client.get("/api/ai/history", headers=hs)).json()
    assert [m["role"] for m in hist] == ["user", "assistant"]

    # broadcast preview sanitizes
    r = await client.post("/api/admin/broadcast/preview", headers=ha, json={"html": "<b>Hi</b><script>x</script>"})
    assert r.json()["html"] == "<b>Hi</b>x"
    n = (await client.post("/api/admin/broadcast/count", headers=ha, json={"langs": ["uz"], "linked": None})).json()["count"]
    assert n >= 1

    # ban → student locked out
    assert (await client.patch("/api/admin/users/77", headers=ha, json={"is_banned": True})).status_code == 200
    assert (await client.get("/api/me", headers=hs)).status_code == 403
    # cannot demote yourself
    assert (await client.patch("/api/admin/users/1", headers=ha, json={"is_admin": False})).status_code == 400

    # maintenance mode
    await client.put("/api/admin/settings", headers=ha, json={"maintenance": True})
    assert (await client.get("/api/me", headers=auth(42))).status_code == 503
    assert (await client.get("/api/me", headers=ha)).status_code == 200
    await client.put("/api/admin/settings", headers=ha, json={"maintenance": False, "ai_daily_limit": 30})


async def test_static_apps(client):
    for path in ("/app/", "/admin/", "/shared/glass.css", "/shared/core.js", "/shared/logo.png", "/app/app.js", "/admin/app.js"):
        assert (await client.get(path)).status_code == 200, path
