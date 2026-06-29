"""Claude(Anthropic) 연동 — 실시간 응대 + 통화 분석.

ANTHROPIC_API_KEY 가 없거나 호출이 실패하면 규칙 기반 폴백으로 동작하므로
키 없이도 전체 파이프라인을 시연/테스트할 수 있습니다.
"""
from __future__ import annotations

import json
import logging

from .config import get_settings
from .models import DEFAULT_TEAMS
from . import routing

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------
_TEAM_LINES = "\n".join(f"- {t['key']}: {t['name']} — {t['description']}" for t in DEFAULT_TEAMS)

_REPLY_SYSTEM = f"""당신은 회사 대표번호의 친절한 AI 전화 상담원입니다.
목표: 전화한 고객의 용건을 짧고 명확하게 파악해서 담당 팀이 처리할 수 있도록 정보를 모읍니다.

규칙:
- 항상 한국어 존댓말로, 한 번에 한 가지만 질문하세요.
- 답변은 두 문장 이내로 짧게(음성으로 읽히므로).
- 용건/핵심 정보가 충분히 모이면 정중히 마무리하고 should_end=true.
- 고객이 그만하겠다거나 더 없다고 하면 should_end=true.

처리 가능한 팀:
{_TEAM_LINES}

반드시 아래 JSON만 출력하세요:
{{"reply": "<고객에게 말할 문장>", "should_end": <true|false>}}"""

_ANALYZE_SYSTEM = f"""당신은 콜센터 통화 기록 분석가입니다.
주어진 통화 전문을 읽고, 담당 팀 배정과 업무 요약을 작성하세요.

가능한 팀(key):
{_TEAM_LINES}

반드시 아래 JSON만 출력하세요:
{{"team_key": "<위 key 중 하나>",
  "title": "<업무 한 줄 제목>",
  "summary": "<담당자가 바로 이해할 3~4문장 요약>",
  "intent": "<핵심 용건 한 단어/짧은 구>",
  "priority": "<low|normal|high|urgent>"}}"""


def _client():
    from anthropic import Anthropic

    return Anthropic(api_key=get_settings().anthropic_api_key)


def _extract_json(text: str) -> dict:
    """모델 출력에서 첫 JSON 객체를 파싱."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------------------
# 1) 실시간 대화 턴
# ---------------------------------------------------------------------------
def next_turn(history: list[dict], turn_index: int, max_turns: int) -> dict:
    """대화 이력을 받아 다음 상담원 발화와 종료 여부를 반환.

    history: [{"role": "caller"|"agent", "text": str}, ...]
    반환: {"reply": str, "should_end": bool}
    """
    settings = get_settings()
    forced_end = turn_index >= max_turns - 1

    if settings.llm_enabled:
        try:
            messages = []
            for m in history:
                role = "user" if m["role"] == "caller" else "assistant"
                messages.append({"role": role, "content": m["text"]})
            # 대화는 고객(user) 발화로 끝나야 함
            if not messages or messages[-1]["role"] != "user":
                messages.append({"role": "user", "content": "(무응답)"})

            resp = _client().messages.create(
                model=settings.reply_model,
                max_tokens=300,
                system=_REPLY_SYSTEM,
                messages=messages,
            )
            data = _extract_json(resp.content[0].text)
            reply = str(data.get("reply", "")).strip() or _fallback_reply(history)
            should_end = bool(data.get("should_end", False)) or forced_end
            return {"reply": reply, "should_end": should_end}
        except Exception as exc:  # pragma: no cover - 외부 호출 방어
            log.warning("next_turn LLM 실패, 폴백 사용: %s", exc)

    return {"reply": _fallback_reply(history), "should_end": forced_end}


def _fallback_reply(history: list[dict]) -> str:
    """LLM 없이도 동작하는 단순 응대 스크립트."""
    caller_turns = [m for m in history if m["role"] == "caller"]
    if len(caller_turns) <= 1:
        return "네, 어떤 일로 전화 주셨는지 말씀해 주시겠어요?"
    if len(caller_turns) == 2:
        return "말씀 감사합니다. 조금 더 자세히 설명해 주시겠어요?"
    return "확인했습니다. 담당 팀에 전달해 빠르게 도와드리겠습니다. 감사합니다."


# ---------------------------------------------------------------------------
# 2) 통화 종료 후 분석/팀 배정
# ---------------------------------------------------------------------------
def analyze_call(transcript: str) -> dict:
    """통화 전문 -> {team_key, team 분류, title, summary, intent, priority}."""
    settings = get_settings()

    if settings.llm_enabled and transcript.strip():
        try:
            resp = _client().messages.create(
                model=settings.analysis_model,
                max_tokens=500,
                system=_ANALYZE_SYSTEM,
                messages=[{"role": "user", "content": transcript}],
            )
            data = _extract_json(resp.content[0].text)
            return {
                "team_key": routing.normalize_team_key(data.get("team_key")),
                "title": str(data.get("title", "")).strip() or "전화 문의",
                "summary": str(data.get("summary", "")).strip() or transcript[:300],
                "intent": str(data.get("intent", "")).strip() or "문의",
                "priority": _norm_priority(data.get("priority")),
            }
        except Exception as exc:  # pragma: no cover
            log.warning("analyze_call LLM 실패, 폴백 사용: %s", exc)

    return _fallback_analysis(transcript)


def _norm_priority(value) -> str:
    value = str(value or "").strip().lower()
    return value if value in {"low", "normal", "high", "urgent"} else "normal"


def _fallback_analysis(transcript: str) -> dict:
    team_key = routing.keyword_route(transcript)
    caller_text = " ".join(
        line.split("고객:", 1)[1].strip()
        for line in transcript.splitlines()
        if line.startswith("고객:")
    )
    snippet = (caller_text or transcript).strip()
    title = (snippet[:40] + "…") if len(snippet) > 40 else (snippet or "전화 문의")
    return {
        "team_key": team_key,
        "title": title or "전화 문의",
        "summary": snippet[:300] or "통화 내용 없음",
        "intent": "문의",
        "priority": routing.estimate_priority(transcript),
    }
