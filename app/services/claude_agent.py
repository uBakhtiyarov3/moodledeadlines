"""Claude as the assistant's engine (Anthropic API), with the same tools as the Gemini agent.

Chosen per chat by the admin setting `ai_engine` (see ai.engine_for). Needs ANTHROPIC_API_KEY; the
key's usage is billed to that Anthropic Console account (a claude.ai subscription can't be used by a
server). Voice and video aren't Claude inputs, so those turns stay on Gemini.
"""

import base64
import json
import logging

from app.config import get_settings

log = logging.getLogger(__name__)

MAX_STEPS = 8
_client = None


def available() -> bool:
    return bool(get_settings().anthropic_api_key)


def client():
    global _client
    if _client is None:
        from anthropic import AsyncAnthropic

        _client = AsyncAnthropic(api_key=get_settings().anthropic_api_key, timeout=180, max_retries=2)
    return _client


def can_read(media: list) -> bool:
    """Claude reads images, PDFs and text; voice/video stay with Gemini."""
    return all(m.kind == "image" or m.mime in ("application/pdf", "text/plain") for m in media or [])


def _messages(turns: list[dict]) -> list[dict]:
    msgs: list[dict] = []
    for turn in turns:
        content = []
        for m in turn.get("media", []):
            data = base64.b64encode(m.data).decode()
            if m.kind == "image":
                content.append({"type": "image", "source": {"type": "base64", "media_type": m.mime, "data": data}})
            elif m.mime == "application/pdf":
                content.append({"type": "document", "source": {"type": "base64", "media_type": m.mime, "data": data}})
            elif m.mime == "text/plain":
                content.append({"type": "text", "text": m.data.decode(errors="ignore")})
        if turn.get("text"):
            content.append({"type": "text", "text": turn["text"]})
        if not content:
            content = [{"type": "text", "text": "(attachment)"}]
        role = "assistant" if turn["role"] == "assistant" else "user"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"].extend(content)
        else:
            msgs.append({"role": role, "content": content})
    return msgs


def _tools(declarations: list[dict] | None) -> list[dict]:
    """Gemini function declarations → Claude tool definitions (the schemas are plain JSON Schema)."""
    return [{"name": d["name"], "description": d["description"],
             "input_schema": d.get("parameters") or {"type": "object", "properties": {}}}
            for d in declarations or []]


async def run(system: str, turns: list[dict], ctx, declarations: list[dict] | None):
    """Stream Claude's answer, running tools between turns. Yields text chunks and ai.Status."""
    import anthropic

    from app.i18n import t
    from app.services import agent
    from app.services import settings as rt
    from app.services.ai import AIUnavailable, Status

    messages = _messages(turns)
    tools = _tools(declarations)
    said = False
    for step in range(MAX_STEPS):
        params = {
            "model": rt.get("claude_model") or "claude-opus-5-5",
            "max_tokens": 16000,
            "system": system,
            "messages": messages,
            "output_config": {"effort": rt.get("claude_effort") or "medium"},
            "cache_control": {"type": "ephemeral"},
            # a policy decline is retried server-side on a suitable model instead of failing the turn
            "betas": ["server-side-fallback-2026-07-01"],
            "fallbacks": "default",
        }
        if tools and step < MAX_STEPS - 1:
            params["tools"] = tools
        gap = said
        try:
            async with client().beta.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    if not text:
                        continue
                    if gap:
                        yield "\n\n"
                        gap = False
                    said = True
                    yield text
                final = await stream.get_final_message()
        except anthropic.RateLimitError as e:
            log.warning("claude rate limited: %s", e)
            raise AIUnavailable("busy") from e
        except anthropic.APIStatusError as e:
            log.warning("claude %s: %s", e.status_code, str(e)[:300])
            raise AIUnavailable("busy" if e.status_code >= 500 or e.status_code == 529 else "error") from e
        except anthropic.APIConnectionError as e:
            raise AIUnavailable("busy") from e

        if final.stop_reason == "refusal":
            if not said:
                yield ""  # ask_stream turns an empty answer into the polite refusal text
            return
        calls = [b for b in final.content if b.type == "tool_use"]
        if not calls:
            return
        # the whole assistant turn goes back unchanged (thinking blocks are tied to it)
        messages.append({"role": "assistant", "content": final.content})
        results = []
        for block in calls:
            yield Status(f"⚙️ {t('agent_working', ctx.user.lang)}")
            result = await agent.call(ctx, block.name, dict(block.input or {}))
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str)[:60000],
                            "is_error": "error" in result})
        messages.append({"role": "user", "content": results})
