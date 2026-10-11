"""AI assistant on Amazon Bedrock (Claude via the Messages API)."""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from anthropic import AsyncAnthropicBedrock
from sqlalchemy import select

from app.config import get_settings
from app.db import Session
from app.models import ChatMessage, Deadline, User
from app.services import kb
from app.services import settings as rt

log = logging.getLogger(__name__)

HISTORY_TURNS = 10
_client: AsyncAnthropicBedrock | None = None


class AIUnavailable(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code  # disabled / limit / error


def client() -> AsyncAnthropicBedrock:
    global _client
    if _client is None:
        # bedrock-runtime (InvokeModel) client — the endpoint Claude Opus 4.5 is served on.
        # Credentials come from the standard AWS chain (env AWS_ACCESS_KEY_ID/...,
        # ~/.aws, or an attached role).
        _client = AsyncAnthropicBedrock(aws_region=get_settings().aws_region)
    return _client


def today() -> str:
    return datetime.now(ZoneInfo(get_settings().timezone)).strftime("%Y-%m-%d")


async def _deadline_context(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    tz = ZoneInfo(get_settings().timezone)
    async with Session() as s:
        rows = (
            await s.execute(
                select(Deadline)
                .where(
                    Deadline.user_id == user_id,
                    Deadline.due_at > now,
                    Deadline.completed.is_(False),
                    Deadline.hidden.is_(False),
                    Deadline.gone.is_(False),
                )
                .order_by(Deadline.due_at)
                .limit(10)
            )
        ).scalars().all()
    if not rows:
        return "The student has no upcoming Moodle deadlines tracked."
    lines = [f"- {d.title} ({d.course}) — due {d.due_at.astimezone(tz):%Y-%m-%d %H:%M}" for d in rows]
    return "The student's upcoming Moodle deadlines:\n" + "\n".join(lines)


async def ask(user: User, question: str) -> str:
    if not rt.get("ai_enabled"):
        raise AIUnavailable("disabled")
    question = question.strip()[:4000]

    async with Session() as s:
        u = await s.get(User, user.id)
        today_ = today()
        if u.ai_day != today_:
            u.ai_day, u.ai_used_today = today_, 0
        if not u.is_admin and u.ai_used_today >= int(rt.get("ai_daily_limit")):
            raise AIUnavailable("limit")
        history = (
            await s.execute(
                select(ChatMessage)
                .where(ChatMessage.user_id == user.id)
                .order_by(ChatMessage.id.desc())
                .limit(HISTORY_TURNS * 2)
            )
        ).scalars().all()[::-1]

        hits = kb.search(question)
        knowledge = "\n\n".join(f"[{h.doc_title}]\n{h.text}" for h in hits) or "(no matching excerpts)"
        now_local = datetime.now(ZoneInfo(get_settings().timezone))
        # Stable instructions first (cacheable), per-request context after.
        system = [
            {"type": "text", "text": rt.CORE_PROMPT},
            {
                "type": "text",
                "text": f"<admin_notes>\n{rt.get('ai_system_prompt')}\n</admin_notes>",
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": (
                    f"Current time (Tashkent): {now_local:%Y-%m-%d %H:%M}. "
                    f"Student's interface language: {u.lang}.\n\n"
                    f"<knowledge_base>\n{knowledge}\n</knowledge_base>\n\n"
                    f"<student_deadlines>\n{await _deadline_context(user.id)}\n</student_deadlines>"
                ),
            },
        ]
        messages = [{"role": m.role, "content": m.content} for m in history]
        # The API requires alternating roles starting with "user"
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        messages.append({"role": "user", "content": question})

        try:
            resp = await client().messages.create(
                model=get_settings().bedrock_model_id,
                max_tokens=get_settings().ai_max_tokens,
                system=system,
                messages=messages,
            )
        except Exception:  # noqa: BLE001
            log.exception("bedrock call failed")
            raise AIUnavailable("error")

        if resp.stop_reason == "refusal":
            answer = {
                "uz": "Kechirasiz, bu savolga javob bera olmayman.",
                "ru": "Извините, я не могу ответить на этот вопрос.",
                "en": "Sorry, I can't help with that request.",
            }.get(u.lang, "Sorry, I can't help with that request.")
        else:
            answer = "".join(b.text for b in resp.content if b.type == "text").strip() or "…"

        s.add(ChatMessage(user_id=user.id, role="user", content=question))
        s.add(ChatMessage(user_id=user.id, role="assistant", content=answer))
        u.ai_used_today += 1
        await s.commit()
    return answer
