"""AI assistant. Default provider: Google Gemini (free tier; text + image + audio).
Alternative: Claude on Amazon Bedrock (text + image), via AI_PROVIDER=bedrock."""

import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.db import Session
from app.models import ChatMessage, Deadline, User
from app.services import kb
from app.services import settings as rt

log = logging.getLogger(__name__)

HISTORY_TURNS = 10
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_client = None

REFUSAL = {
    "uz": "Kechirasiz, bu savolga javob bera olmayman. UWED, o'qish yoki deadlinelar haqida so'rang.",
    "ru": "Извините, на этот вопрос я ответить не могу. Спросите об UWED, учёбе или дедлайнах.",
    "en": "Sorry, I can't help with that. Ask me about UWED, your studies or deadlines.",
}
# What gets stored in the chat history in place of the media itself
MEDIA_LABEL = {"image": "[🖼 rasm / image]", "audio": "[🎤 ovozli xabar / voice message]", "document": "[📄 PDF]"}


class AIUnavailable(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code  # disabled / limit / busy / unsupported / error


@dataclass
class Media:
    kind: str  # "image" | "audio" | "document" (PDF)
    mime: str  # e.g. image/jpeg, audio/ogg
    data: bytes


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


MEDIA_HINT = (
    "\n\n<media_handling>\n"
    "- Voice message: understand what the student says (Uzbek, Russian or English, possibly mixed) and "
    "answer it directly. Do not transcribe it back unless asked.\n"
    "- PDF / image of a document: usually the assignment brief or the student's own draft — review it "
    "under <tutor_mode>.\n"
    "- Image: it may be an assignment, a page, a screenshot or the student's own work. Describe only "
    "what's needed; apply <tutor_mode> — explain and review, never solve graded tasks for them.\n"
    "</media_handling>"
)


# ---------------------------------------------------------------- providers

def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10))


async def _gemini_generate(system: str, turns: list[dict]) -> str:
    """turns: [{"role": "user"|"assistant", "text": str, "media": [Media]}]"""
    st = get_settings()
    if not st.gemini_api_key:
        raise AIUnavailable("error")
    contents = []
    for turn in turns:
        parts = [{"inline_data": {"mime_type": m.mime, "data": base64.b64encode(m.data).decode()}} for m in turn.get("media", [])]
        if turn["text"]:
            parts.append({"text": turn["text"]})
        role = "model" if turn["role"] == "assistant" else "user"
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": st.gemini_max_tokens},
    }
    if st.gemini_thinking_level:
        body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": st.gemini_thinking_level}
    models = [st.gemini_model] + [m.strip() for m in st.gemini_fallback_models.split(",") if m.strip()]
    r = None
    async with _http() as c:
        for model in dict.fromkeys(models):  # de-duplicated, order kept
            try:
                r = await c.post(
                    GEMINI_URL.format(model=model),
                    headers={"x-goog-api-key": st.gemini_api_key},
                    json=body,
                )
                if r.status_code == 400 and "thinking" in r.text.lower():
                    # this model doesn't accept the thinking level → use its default
                    plain = {**body, "generationConfig": {"maxOutputTokens": st.gemini_max_tokens}}
                    r = await c.post(
                        GEMINI_URL.format(model=model),
                        headers={"x-goog-api-key": st.gemini_api_key},
                        json=plain,
                    )
            except httpx.TimeoutException:
                log.warning("gemini %s timeout", model)
                continue
            if r.status_code in (429, 500, 503, 504):
                # overloaded / rate limited → try the next model
                log.warning("gemini %s %s, falling back", model, r.status_code)
                continue
            break
    if r is None or r.status_code in (402, 429, 500, 503, 504):
        # 402 = prepaid credits used up on a billing-enabled project
        if r is not None:
            log.warning("gemini %s: %s", r.status_code, r.text[:300])
        raise AIUnavailable("busy")
    data = r.json()
    if (data.get("promptFeedback") or {}).get("blockReason"):
        return ""
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = (cands[0].get("content") or {}).get("parts") or []
    # skip "thought" parts some models return
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()


def client():
    """Bedrock client (only used with AI_PROVIDER=bedrock)."""
    global _client
    if _client is None:
        from anthropic import AsyncAnthropicBedrock

        _client = AsyncAnthropicBedrock(aws_region=get_settings().aws_region)
    return _client


async def _bedrock_generate(system: str, turns: list[dict]) -> str:
    messages = []
    for turn in turns:
        content = []
        for m in turn.get("media", []):
            if m.kind != "image":
                raise AIUnavailable("unsupported")
            content.append({"type": "image", "source": {"type": "base64", "media_type": m.mime, "data": base64.b64encode(m.data).decode()}})
        content.append({"type": "text", "text": turn["text"] or "(see attachment)"})
        if messages and messages[-1]["role"] == turn["role"]:
            messages[-1]["content"].extend(content)
        else:
            messages.append({"role": turn["role"], "content": content})
    resp = await client().messages.create(
        model=get_settings().bedrock_model_id,
        max_tokens=get_settings().ai_max_tokens,
        system=system,
        messages=messages,
    )
    if resp.stop_reason == "refusal":
        return ""
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ---------------------------------------------------------------- public API

async def ask(user: User, question: str, media: list[Media] | None = None) -> str:
    if not rt.get("ai_enabled"):
        raise AIUnavailable("disabled")
    media = media or []
    question = (question or "").strip()[:4000]
    provider = get_settings().ai_provider

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

        hits = kb.search(question or " ".join(m.content for m in history[-2:]))
        knowledge = "\n\n".join(f"[{h.doc_title}]\n{h.text}" for h in hits) or "(no matching excerpts)"
        now_local = datetime.now(ZoneInfo(get_settings().timezone))
        system = (
            rt.CORE_PROMPT
            + MEDIA_HINT
            + f"\n\n<admin_notes>\n{rt.get('ai_system_prompt')}\n</admin_notes>\n\n"
            + f"Current time (Tashkent): {now_local:%Y-%m-%d %H:%M}. Student's interface language: {u.lang}.\n\n"
            + f"<knowledge_base>\n{knowledge}\n</knowledge_base>\n\n"
            + f"<student_deadlines>\n{await _deadline_context(user.id)}\n</student_deadlines>"
        )
        turns = [{"role": m.role, "text": m.content} for m in history]
        while turns and turns[0]["role"] != "user":
            turns.pop(0)
        turns.append({"role": "user", "text": question, "media": media})

        try:
            if provider == "bedrock":
                answer = await _bedrock_generate(system, turns)
            else:
                answer = await _gemini_generate(system, turns)
        except AIUnavailable:
            raise
        except Exception:  # noqa: BLE001
            log.exception("%s call failed", provider)
            raise AIUnavailable("error")
        answer = answer or REFUSAL.get(u.lang, REFUSAL["en"])

        stored_q = " ".join(filter(None, [*(MEDIA_LABEL[m.kind] for m in media), question]))
        s.add(ChatMessage(user_id=user.id, role="user", content=stored_q))
        s.add(ChatMessage(user_id=user.id, role="assistant", content=answer))
        u.ai_used_today += 1
        await s.commit()
    return answer
