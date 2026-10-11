"""Bot handler smoke tests: updates go through the real dispatcher, Telegram calls are captured."""

from datetime import datetime, timezone

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from tests.test_api import client  # noqa: F401  (fixture: app lifespan + fake Moodle)


@pytest.fixture
async def tg(client, monkeypatch):  # noqa: F811
    from app.bot.handlers import UserMiddleware, router

    calls: list = []

    async def fake_call(self, method, request_timeout=None):
        calls.append(method)
        return True

    monkeypatch.setattr(Bot, "__call__", fake_call)
    bot = Bot("123:TEST")
    dp = Dispatcher()
    dp.message.outer_middleware(UserMiddleware())
    dp.callback_query.outer_middleware(UserMiddleware())
    router._parent_router = None  # allow re-attaching between tests
    dp.include_router(router)
    n = iter(range(1, 10_000))

    async def send(text=None, callback=None, uid=900):
        user = {"id": uid, "is_bot": False, "first_name": "Aziz", "language_code": "uz"}
        chat = {"id": uid, "type": "private"}
        msg = {"message_id": next(n), "date": int(datetime.now(timezone.utc).timestamp()), "chat": chat, "from": user, "text": text or "x"}
        if callback:
            upd = {"update_id": next(n), "callback_query": {"id": "1", "from": user, "chat_instance": "c", "data": callback, "message": msg}}
        else:
            upd = {"update_id": next(n), "message": msg}
        calls.clear()
        await dp.feed_update(bot, Update.model_validate(upd, context={"bot": bot}))
        return calls

    yield send


def texts(calls):
    return [getattr(c, "text", None) for c in calls if type(c).__name__ == "SendMessage"]


async def test_start_lang_link_and_ai(tg, monkeypatch):
    out = await tg("/start")
    assert "Tilni tanlang" in texts(out)[0]

    out = await tg(callback="lang:en")
    assert any("Hi, <b>Aziz</b>" in (t or "") for t in texts(out))

    out = await tg("/deadlines")
    assert "Moodle isn't connected" in texts(out)[0]

    url = "https://moodle.uwed.uz/calendar/export_execute.php?userid=5&authtoken=" + "d" * 32
    out = await tg(f"here: {url}")
    assert "Moodle connected" in texts(out)[0]
    assert any(type(c).__name__ == "DeleteMessage" for c in out)  # token-bearing message removed

    out = await tg("/deadlines")
    assert "Essay due" in texts(out)[0]

    from app.services import ai

    async def fake_ask(user, q):
        return "**Salom!**"

    monkeypatch.setattr(ai, "ask", fake_ask)
    out = await tg("Kutubxona qayerda?")
    assert texts(out) == ["<b>Salom!</b>"]


async def test_banned_user_blocked(tg):
    from app.db import Session
    from app.models import User

    await tg("/start", uid=901)
    async with Session() as s:
        (await s.get(User, 901)).is_banned = True
        await s.commit()
    out = await tg("hello", uid=901)
    assert "blocked" in texts(out)[0] or "bloklangan" in texts(out)[0]
