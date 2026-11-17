"""Voice messages and personalised messages that the admin agent sends to people.

- send_voice: the given text, spoken by the bot's voice, as a Telegram voice message.
- personalised: for each recipient, the AI writes its own message from the admin's instruction and that
  person's profile (name, language, studies, deadlines…), then sends it as text and/or voice. Runs in the
  background and reports to the admin when done.
"""

import asyncio
import logging

from aiogram import Bot
from aiogram.methods import SendVoice
from aiogram.types import BufferedInputFile
from sqlalchemy import select

from app.db import Session
from app.models import User

log = logging.getLogger(__name__)

CONCURRENCY = 3
MAX_RECIPIENTS = 5000
_jobs: set[asyncio.Task] = set()

WRITER_PROMPT = """You write one Telegram message from UWED Pulse (the university's student assistant bot) to one
student, following the administrator's instruction. Make it personal: use their first name, write in their
language, and fit the content to what you know about them (studies, courses, upcoming deadlines). Warm,
concise (40-120 words), no greeting formulas like "Dear user". Telegram Markdown: **bold**, *italic*, lists.
Uzbek: write it in the new Uzbek Latin alphabet (ö, ğ, ş, ç). Output only the message itself."""


async def voice_of(text: str) -> bytes | None:
    from app.services import tts

    return await tts.synthesize(text)


async def send_voice(bot: Bot, chat_id: int, text: str, caption: str | None = None) -> dict:
    ogg = await voice_of(text)
    if not ogg:
        return {"error": "the voice could not be generated right now"}
    try:
        await bot(SendVoice(chat_id=chat_id, voice=BufferedInputFile(ogg, "pulse.ogg"), caption=caption or None))
    except Exception as e:  # noqa: BLE001
        return {"error": f"Telegram: {str(e)[:200]}"}
    return {"ok": True}


async def write_for(user: User, instruction: str) -> str:
    """The AI's message for this one person."""
    from app.services import ai, profile

    about = await profile.context(user)
    deadlines = await ai._deadline_context(user.id)
    turn = (f"Administrator's instruction:\n{instruction}\n\n"
            f"The student (interface language: {user.lang}):\n{about}\n\n{deadlines}")
    return (await ai._gemini_generate(WRITER_PROMPT, [{"role": "user", "text": turn}])).strip()


async def recipients(user_ids: list[int] | None, segment: dict) -> list[User]:
    from app.services import broadcast

    async with Session() as s:
        if user_ids:
            q = select(User).where(User.id.in_([int(u) for u in user_ids]), User.is_banned.is_(False))
        else:
            q = select(User).where(User.id.in_(broadcast.segment_query(segment)))
        return (await s.execute(q.limit(MAX_RECIPIENTS))).scalars().all()


async def personalised(bot: Bot, admin: User, instruction: str, people: list[User], voice: bool, text: bool) -> dict:
    from app.bot import rich
    from app.services import outbox

    sem = asyncio.Semaphore(CONCURRENCY)
    done, failed = [], []

    async def one(u: User):
        async with sem:
            try:
                msg = await write_for(u, instruction)
                if not msg:
                    raise RuntimeError("empty message")
                if text:
                    await rich.send(bot, u.id, msg)
                if voice:
                    r = await send_voice(bot, u.id, msg)
                    if "error" in r:
                        raise RuntimeError(r["error"])
                await outbox.log(admin.id, "personalised " + "+".join(k for k, on in (("text", text), ("voice", voice)) if on),
                                 u.id, msg)
                done.append(u.id)
            except Exception as e:  # noqa: BLE001
                log.info("personalised message to %s failed: %s", u.id, e)
                failed.append(u.id)
            await asyncio.sleep(0.2)

    await asyncio.gather(*(one(u) for u in people))
    return {"sent": len(done), "failed": len(failed), "failed_ids": failed[:50]}


def start_personalised(bot: Bot, admin: User, instruction: str, people: list[User], voice: bool, text: bool) -> None:
    """Run in the background; tell the admin the result in Telegram."""
    from app.bot import rich

    async def job():
        try:
            r = await personalised(bot, admin, instruction, people, voice, text)
            note = f"✅ Şaxsiy xabarlar yuborildi: **{r['sent']}** ta" + (f", xato: {r['failed']} ta" if r["failed"] else "")
        except Exception:  # noqa: BLE001
            log.exception("personalised job failed")
            note = "⚠️ Şaxsiy xabarlarni yuboriş töxtab qoldi"
        try:
            await rich.send(bot, admin.id, note)
        except Exception:  # noqa: BLE001
            pass

    task = asyncio.create_task(job())
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)
