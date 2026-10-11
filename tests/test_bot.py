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

    async def send(text=None, callback=None, uid=900, photo=False, voice=None, sticker=False, reply_to=None):
        user = {"id": uid, "is_bot": False, "first_name": "Aziz", "language_code": "uz"}
        chat = {"id": uid, "type": "private"}
        msg = {"message_id": next(n), "date": int(datetime.now(timezone.utc).timestamp()), "chat": chat, "from": user}
        if photo:
            msg["photo"] = [{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}]
            if text:
                msg["caption"] = text
        elif voice is not None:
            msg["voice"] = {"file_id": "v", "file_unique_id": "uv", "duration": voice, "mime_type": "audio/ogg"}
        elif sticker:
            msg["sticker"] = {"file_id": "s", "file_unique_id": "us", "type": "regular", "width": 1, "height": 1, "is_animated": False, "is_video": False}
        else:
            msg["text"] = text or "x"
        if reply_to:
            msg["reply_to_message"] = {"message_id": reply_to, "date": msg["date"], "chat": chat}
        if callback:
            upd = {"update_id": next(n), "callback_query": {"id": "1", "from": user, "chat_instance": "c", "data": callback, "message": msg}}
        else:
            upd = {"update_id": next(n), "message": msg}
        calls.clear()
        await dp.feed_update(bot, Update.model_validate(upd, context={"bot": bot}))
        return calls

    yield send


def texts(calls):
    """Text of every message the bot sent (classic or rich; streamed drafts excluded)."""
    out = []
    for c in calls:
        kind = type(c).__name__
        if kind == "SendMessage":
            out.append(c.text)
        elif kind == "SendRichMessage":
            out.append(c.rich_message.markdown)
    return out


def stream_of(answer: str):
    async def fake_stream(user, q, media=None):
        for word in answer.split(" "):
            yield word + " "

    return fake_stream


async def test_start_lang_link_and_ai(tg, monkeypatch):
    out = await tg("/start")
    assert "Tilni tanlang" in texts(out)[0]

    out = await tg(callback="lang:en")
    assert any("# 👋 Hi, Aziz!" in (t or "") for t in texts(out))

    out = await tg("/deadlines")
    assert "Moodle isn't connected" in texts(out)[0]

    url = "https://moodle.uwed.uz/calendar/export_execute.php?userid=5&authtoken=" + "d" * 32
    out = await tg(f"here: {url}")
    assert "Moodle connected" in texts(out)[0]
    assert any(type(c).__name__ == "DeleteMessage" for c in out)  # token-bearing message removed

    out = await tg("/deadlines")
    table = texts(out)[0]
    assert "**Essay due**" in table and "| 🔴 |" in table and "tg://time?unix=" in table

    from app.services import ai

    monkeypatch.setattr(ai, "ask_stream", stream_of("**Salom!** Qanday yordam kerak?"))
    out = await tg("Kutubxona qayerda?")
    kinds = [type(c).__name__ for c in out]
    assert kinds[0] == "SendRichMessageDraft"  # "thinking…" shown immediately
    assert texts(out) == ["**Salom!** Qanday yordam kerak?"]  # final answer as one rich message


async def test_banned_user_blocked(tg):
    from app.db import Session
    from app.models import User

    await tg("/start", uid=901)
    async with Session() as s:
        (await s.get(User, 901)).is_banned = True
        await s.commit()
    out = await tg("hello", uid=901)
    assert "blocked" in texts(out)[0] or "bloklangan" in texts(out)[0]


async def test_ai_new_and_non_text(tg):
    from sqlalchemy import func, select

    from app.db import Session
    from app.models import ChatMessage

    await tg("/start", uid=902)
    async with Session() as s:
        s.add(ChatMessage(user_id=902, role="user", content="old"))
        await s.commit()
    out = await tg("/ai", uid=902)
    assert "UWED Pulse AI" in texts(out)[0]
    out = await tg("/new", uid=902)
    assert "Yangi suhbat" in texts(out)[0]
    async with Session() as s:
        assert (await s.execute(select(func.count(ChatMessage.id)).where(ChatMessage.user_id == 902))).scalar_one() == 0
    out = await tg(sticker=True, uid=902)
    assert "PDF yuboring" in texts(out)[0]


async def test_voice_and_photo_go_to_ai(tg, monkeypatch):
    from app.bot import handlers
    from app.services import ai

    got = []

    async def fake_download(bot, file_id):
        return b"bytes-of-" + file_id.encode()

    async def fake_ask(user, q, media=None):
        got.append((q, [(m.kind, m.mime, m.data) for m in media or []]))
        yield "javob"

    spoken = []

    async def fake_tts(text):
        spoken.append(text)
        return b"OggS-voice"

    monkeypatch.setattr(handlers, "download", fake_download)
    monkeypatch.setattr(ai, "ask_stream", fake_ask)
    monkeypatch.setattr(handlers.tts, "synthesize", fake_tts)
    monkeypatch.setattr(handlers.tts, "enabled", lambda: True)
    await tg("/start", uid=903)
    out = await tg(voice=12, uid=903)
    assert texts(out) == ["javob"] and got[-1] == ("", [("audio", "audio/ogg", b"bytes-of-v")])
    # voice question → text answer first, then a voice note
    names = [type(c).__name__ for c in out]
    assert names.index("SendRichMessage") < names.index("SendVoice") and spoken == ["javob"]
    out = await tg("shu insho qanday?", photo=True, uid=903)
    assert got[-1] == ("shu insho qanday?", [("image", "image/jpeg", b"bytes-of-f")])
    assert "SendVoice" not in [type(c).__name__ for c in out] and len(spoken) == 1  # photo → no voice
    out = await tg(voice=3600, uid=903)
    assert "juda uzun" in texts(out)[0] and len(got) == 2


def test_split_message():
    from app.bot.handlers import split_message

    text = "\n".join(f"line {i} " + "x" * 90 for i in range(100))
    parts = split_message(text)
    assert all(len(p) <= 3500 for p in parts) and "\n".join(parts) == text
    assert split_message("short") == ["short"]


async def test_burst_of_updates_from_new_user(tg):
    """Many queued updates from a brand-new user are handled concurrently — none may fail."""
    import asyncio

    results = await asyncio.gather(*(tg("/start", uid=904) for _ in range(8)), return_exceptions=True)
    assert not [r for r in results if isinstance(r, Exception)]


async def test_chat_only_mode_without_https(tg):
    """With a non-HTTPS PUBLIC_URL Telegram rejects web_app buttons, so none may be sent."""
    out = list(await tg("/start", uid=905))
    out += list(await tg(callback="lang:uz", uid=905))
    out += list(await tg("/admin", uid=905))
    for call in out:
        markup = getattr(call, "reply_markup", None)
        assert "web_app" not in (markup.model_dump_json(exclude_none=True) if markup else "")
    assert any("Salom" in (t or "") for t in texts(out))


async def test_settings_button_opens_app_via_inline_button(tg, monkeypatch):
    """Reply-keyboard web_app buttons get no initData, so Settings must go through an inline button."""
    from app.bot import keyboards

    monkeypatch.setattr(keyboards, "app_enabled", lambda: True)
    kb = keyboards.main_kb("uz").model_dump_json(exclude_none=True)
    assert "web_app" not in kb
    await tg("/start", uid=906)
    out = await tg("⚙️ Sozlamalar", uid=906)
    markup = out[-1].reply_markup.model_dump_json(exclude_none=True)
    assert "web_app" in markup and "?p=settings" in markup


async def test_admin_chat_flow(tg, monkeypatch):
    """Student opens the admin chat, writes; admin gets a rich card and answers two ways."""
    from app.db import Session
    from app.models import SupportMessage, SupportRelay
    from app.services import ai, support
    from sqlalchemy import select

    async def no_ai(*a, **kw):
        raise AssertionError("support messages must not reach the AI")
        yield  # pragma: no cover

    monkeypatch.setattr(ai, "ask_stream", no_ai)
    await tg("/start", uid=1)  # admin (ADMIN_IDS=1)
    await tg("/start", uid=910)
    out = await tg("💬 Admin bilan chat", uid=910)
    assert texts(out)[0].startswith("### 💬 Admin bilan chat")
    assert "sup:close" in out[-1].reply_markup.model_dump_json()

    out = await tg("Kontrakt bo'yicha savolim bor", uid=910)
    cards = [c for c in out if type(c).__name__ == "SendRichMessage" and c.chat_id == 1]
    assert cards and "Yangi murojaat" in cards[0].rich_message.markdown
    assert "> Kontrakt bo'yicha savolim bor" in cards[0].rich_message.markdown.replace("\\'", "'")
    assert "sup:reply:910" in cards[0].reply_markup.model_dump_json()
    assert any(type(c).__name__ == "SetMessageReaction" for c in out)  # 👌 to the student

    # admin taps "↩️ Javob berish", then writes
    out = await tg(callback="sup:reply:910", uid=1)
    assert "Javob" in texts(out)[0]
    out = await tg("Dekanatga murojaat qiling, 204-xona", uid=1)
    to_student = [c for c in out if type(c).__name__ == "SendRichMessage" and c.chat_id == 910]
    assert to_student and to_student[0].rich_message.markdown.startswith("### 👨‍💼 Admin")
    assert any("Yuborildi" in (t or "") for t in texts(out))

    # native Telegram reply to a relayed card also works
    async with Session() as s:
        s.add(SupportRelay(admin_id=1, message_id=555, user_id=910))
        await s.commit()
    out = await tg("Yana bir narsa", uid=1, reply_to=555)
    assert any(type(c).__name__ == "SendRichMessage" and c.chat_id == 910 for c in out)
    async with Session() as s:
        rows = (await s.execute(select(SupportMessage).where(SupportMessage.user_id == 910))).scalars().all()
    assert [(m.from_admin, m.text) for m in rows] == [
        (False, "Kontrakt bo'yicha savolim bor"), (True, "Dekanatga murojaat qiling, 204-xona"), (True, "Yana bir narsa")]
    assert await support.relay_target(1, 555) == 910

    # student closes the chat → back to AI
    out = await tg(callback="sup:close", uid=910)
    assert any("yopildi" in (t or "") for t in texts(out))
    assert await support.get_state(910) is None
