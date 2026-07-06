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

    # ClawOps (국내 070 번호 실시간 음성봇)
    clawops_api_key: str = ""
    clawops_account_id: str = ""
    clawops_from_number: str = ""  # 발급받은 070 번호 (예: 07012345678)
    elevenlabs_voice_id: str = "uyVNoMrnUku1dZyVEXwD"  # ElevenLabs 한국어 음성(Anna Kim)

    # App
    database_url: str = "sqlite:///./data/callcenter.db"
    knowledge_file: str = "./knowledge.md"
    knowledge_dir: str = "./knowledge"
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
