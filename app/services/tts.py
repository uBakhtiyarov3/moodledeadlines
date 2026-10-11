"""Voice replies: Gemini text-to-speech → Telegram voice note (OGG/Opus via ffmpeg)."""

import asyncio
import base64
import logging
import re

import httpx

from app.config import get_settings
from app.services import settings as rt

log = logging.getLogger(__name__)

TTS_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_CHARS = 1200
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def speakable(markdown: str) -> str:
    """Strip formatting, links and emoji so the voice reads naturally; cap the length."""
    t = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\|\|.*?\|\|", "", t)  # spoilers stay hidden in voice too
    t = re.sub(r"[*_`~>#|]", "", t)
    t = re.sub(r"^\s*[-•◦]\s+", "", t, flags=re.M)
    t = EMOJI.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    if len(t) > MAX_CHARS:
        cut = t[:MAX_CHARS]
        t = cut[: max(cut.rfind(". "), cut.rfind("\n"), MAX_CHARS // 2) + 1]
    return t


def enabled() -> bool:
    st = get_settings()
    return bool(rt.get("tts_enabled") and st.gemini_api_key and st.gemini_tts_model)


async def _to_ogg(wav: bytes) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k",
        "-application", "voip", "-f", "ogg", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(wav)
    if proc.returncode != 0:
        raise RuntimeError(err.decode(errors="ignore")[:300])
    return out


def request_body(text: str) -> dict:
    st = get_settings()
    return {
        # Only the answer itself: TTS models read any instruction text aloud too
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": st.gemini_tts_voice}}},
        },
    }


async def synthesize(markdown: str) -> bytes | None:
    """Return an OGG/Opus voice note for the answer, or None if anything fails."""
    st = get_settings()
    text = speakable(markdown)
    if not text:
        return None
    body = request_body(text)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as c:
            r = await c.post(
                TTS_URL.format(model=st.gemini_tts_model),
                headers={"x-goog-api-key": st.gemini_api_key},
                json=body,
            )
        if r.status_code != 200:
            log.warning("tts %s: %s", r.status_code, r.text[:300])
            return None
        part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        audio = base64.b64decode(part["data"])
        if not audio.startswith(b"RIFF"):  # raw PCM (audio/L16;rate=…)
            return await _pcm_to_ogg(audio, part.get("mimeType", ""))
        return await _to_ogg(audio)
    except Exception:  # noqa: BLE001  (voice is a bonus; the text answer was already sent)
        log.exception("tts failed")
        return None


async def _pcm_to_ogg(pcm: bytes, mime: str) -> bytes:
    rate = re.search(r"rate=(\d+)", mime)
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", rate.group(1) if rate else "24000", "-ac", "1",
        "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k", "-application", "voip", "-f", "ogg", "pipe:1",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(pcm)
    if proc.returncode != 0:
        raise RuntimeError(err.decode(errors="ignore")[:300])
    return out
