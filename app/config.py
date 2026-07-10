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
    clawops_session: str = ""  # "realtime" | "pipeline" | ""(자동)
    clawops_signing_key: str = ""  # 설정 시 /clawops/webhook 서명 검증 활성화
    openai_api_key: str = ""  # 있으면 OpenAI Realtime 세션 사용 (키 1개로 충분)
    openai_realtime_model: str = "gpt-realtime-2"  # Realtime 모델 변경용
    openai_realtime_voice: str = "marin"
    deepgram_model: str = "nova-3"  # 파이프라인 STT 모델 (한국어: nova-3 / nova-2)
    elevenlabs_voice_id: str = "uyVNoMrnUku1dZyVEXwD"  # ElevenLabs 한국어 음성(Anna Kim)

    # App
    database_url: str = "sqlite:///./data/callcenter.db"
    knowledge_file: str = "./knowledge.md"
    knowledge_dir: str = "./knowledge"
    # 회사 업종/사업 맥락 — 음성 인식·용건 이해에 활용
    company_context: str = (
        "주식회사 캠스는 자동차 부품 제조업체로, 플라스틱 사출(injection), 도장(painting), "
        "조립(assembly) 공정을 운영합니다. 주로 자동차 범퍼·크래시패드 등 외장/내장 부품을 "
        "생산합니다. 따라서 전화 문의에는 사출기, 금형, 도장 라인, 조립 라인, 컨베이어, "
        "설비 번호(1호기·2호기 등), 불량·품질, 자재·부품 납기, 협력사, 수주·견적 같은 "
        "제조 현장 용어가 자주 등장합니다."
    )
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
