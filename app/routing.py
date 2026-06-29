"""규칙 기반 팀 분류 (LLM 폴백 / LLM 결과 검증용)."""
from __future__ import annotations

from .models import DEFAULT_TEAMS

VALID_TEAM_KEYS = {t["key"] for t in DEFAULT_TEAMS}
DEFAULT_TEAM_KEY = "general"

# 긴급도 추정용 키워드
_URGENT_WORDS = ["긴급", "당장", "지금 바로", "장애", "전체", "먹통", "전혀", "손해"]
_HIGH_WORDS = ["오류", "에러", "안돼", "안 돼", "환불", "고장", "멈춰"]


def keyword_route(text: str) -> str:
    """키워드 매칭으로 팀 key를 반환. 매칭 없으면 general."""
    if not text:
        return DEFAULT_TEAM_KEY
    lowered = text.lower()
    best_key = DEFAULT_TEAM_KEY
    best_score = 0
    for spec in DEFAULT_TEAMS:
        score = sum(1 for kw in spec["keywords"] if kw.lower() in lowered)
        if score > best_score:
            best_score = score
            best_key = spec["key"]
    return best_key


def estimate_priority(text: str) -> str:
    if not text:
        return "normal"
    lowered = text.lower()
    if any(w in lowered for w in _URGENT_WORDS):
        return "urgent"
    if any(w in lowered for w in _HIGH_WORDS):
        return "high"
    return "normal"


def normalize_team_key(key: str | None) -> str:
    """LLM이 돌려준 team key를 검증하고, 유효하지 않으면 general."""
    if key and key.strip() in VALID_TEAM_KEYS:
        return key.strip()
    return DEFAULT_TEAM_KEY
