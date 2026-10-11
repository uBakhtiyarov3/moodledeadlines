from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    # Public HTTPS base URL where the Mini Apps are served, e.g. https://34-12-1-5.sslip.io
    public_url: str = "http://localhost:8000"
    # Comma separated Telegram user ids with super-admin rights
    admin_ids: list[int] = []
    # Used to derive the encryption key for Moodle URLs/tokens. Keep it secret and stable.
    secret_key: str = "change-me"

    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    timezone: str = "Asia/Tashkent"

    moodle_base: str = "https://moodle.uwed.uz"
    sync_interval_min: int = 30

    # AI provider: "gemini" (default, free tier, text+image+audio) or "bedrock" (Claude)
    ai_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    # Tried in order when the main model is overloaded (503) or rate limited (429)
    gemini_fallback_models: str = "gemini-flash-latest,gemini-flash-lite-latest"
    gemini_max_tokens: int = 8192
    # Gemini 3 "thinking" depth: low = fast & cheap (good for chat); "" = model default
    gemini_thinking_level: str = "low"
    # Voice replies (text-to-speech) to students who ask by voice
    gemini_tts_model: str = "gemini-3.8-flash-tts"
    gemini_tts_voice: str = "Kore"
    # Telegram voice messages longer than this are rejected (seconds)
    ai_max_voice_sec: int = 300

    aws_region: str = "us-east-1"
    # Claude Opus 4.5 via cross-region inference profile (bedrock-runtime endpoint).
    # Plain model id: anthropic.claude-opus-4-5-20251101-v1:0 ; the "us." prefix routes
    # through the US cross-region inference profile, which this model requires.
    bedrock_model_id: str = "us.anthropic.claude-opus-4-5-20251101-v1:0"
    ai_max_tokens: int = 1500

    host: str = "0.0.0.0"
    port: int = 8000
    run_bot: bool = True

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.replace(" ", "").split(",") if x]
        if isinstance(v, int):
            return [v]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
