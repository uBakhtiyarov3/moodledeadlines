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

    # AI: Google Gemini (text, images, PDF, audio, video)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    # Tried in order when the main model is overloaded (503) or rate limited (429)
    gemini_fallback_models: str = "gemini-flash-latest,gemini-flash-lite-latest"
    gemini_max_tokens: int = 8192
    # Gemini 3 "thinking" depth: low = fast & cheap (good for chat); "" = model default
    gemini_thinking_level: str = "low"
    # Small background model that keeps each student's AI memory up to date
    gemini_memory_model: str = "gemini-flash-lite-latest"
    # Voice replies (text-to-speech) to students who ask by voice
    gemini_tts_model: str = "gemini-3.8-flash-tts"
    gemini_tts_voice: str = "Kore"
    # Telegram voice messages longer than this are rejected (seconds)
    ai_max_voice_sec: int = 300


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
