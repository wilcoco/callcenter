"""환경설정 로딩 (.env 지원)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Anthropic / Claude
    anthropic_api_key: str = ""
    reply_model: str = "claude-haiku-4-5-20251001"
    analysis_model: str = "claude-sonnet-4-6"

    # Twilio
    twilio_auth_token: str = ""
    voice_language: str = "ko-KR"
    twilio_voice: str = "Polly.Seoyeon"

    # App
    database_url: str = "sqlite:///./data/callcenter.db"
    knowledge_file: str = "./knowledge.md"
    public_base_url: str = ""
    max_turns: int = 8

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def verify_twilio_signature(self) -> bool:
        return bool(self.twilio_auth_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
