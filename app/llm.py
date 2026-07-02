"""Claude(Anthropic) 연동 — 실시간 응대 + 통화 분석.

ANTHROPIC_API_KEY 가 없거나 호출이 실패하면 규칙 기반 폴백으로 동작하므로
키 없이도 전체 파이프라인을 시연/테스트할 수 있습니다.
"""
from __future__ import annotations

import json
import logging
import os

from .config import get_settings
from .models import DEFAULT_TEAMS
from . import routing

log = logging.getLogger(__name__)

# 지식 문서가 너무 크면 프롬프트 비용/지연이 커지므로 상한을 둠 (약 50k자)
_KNOWLEDGE_MAX_CHARS = 50_000

# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------
_TEAM_LINES = "\n".join(f"- {t['key']}: {t['name']} — {t['description']}" for t in DEFAULT_TEAMS)


# knowledge/ 폴더에서 읽어들일 텍스트 파일 확장자
_KNOWLEDGE_EXTS = {".md", ".txt"}


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("지식 문서 읽기 실패(%s): %s", path, exc)
        return ""


def load_knowledge() -> str:
    """회사 지식 문서를 모두 읽어 하나의 텍스트로 반환.

    - knowledge/ 폴더의 .md/.txt 파일 전부 (파일명 순)
    - (하위호환) 루트의 knowledge.md 단일 파일
    매 통화 턴마다 다시 읽으므로, 파일을 추가/수정하면 재시작 없이 반영됩니다.
    """
    settings = get_settings()
    parts: list[str] = []

    single = settings.knowledge_file
    if single and os.path.isfile(single):
        text = _read_text(single)
        if text:
            parts.append(text)

    directory = settings.knowledge_dir
    if directory and os.path.isdir(directory):
        for name in sorted(os.listdir(directory)):
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            if os.path.splitext(name)[1].lower() not in _KNOWLEDGE_EXTS:
                log.info("지식 폴더의 지원하지 않는 파일 형식을 건너뜀: %s", name)
                continue
            text = _read_text(path)
            if text:
                parts.append(f"[문서: {name}]\n{text}")

    combined = "\n\n---\n\n".join(parts)
    if len(combined) > _KNOWLEDGE_MAX_CHARS:
        log.warning(
            "지식 문서 합계가 %d자로 상한(%d자)을 초과하여 잘라서 사용합니다. "
            "문서가 크면 RAG 방식 도입을 고려하세요.",
            len(combined), _KNOWLEDGE_MAX_CHARS,
        )
        combined = combined[:_KNOWLEDGE_MAX_CHARS]
    return combined


def _knowledge_block() -> str:
    knowledge = load_knowledge()
    if not knowledge:
        return ""
    return f"""

아래는 회사가 제공한 공식 지식 문서입니다. 답변은 반드시 이 문서를 우선 근거로 하세요.
문서에 없는 내용은 추측하지 말고 담당 팀 확인 후 연락드리겠다고 안내하세요.

<회사_지식_문서>
{knowledge}
</회사_지식_문서>"""


def _reply_system() -> str:
    return f"""당신은 회사 대표번호의 친절한 AI 전화 상담원입니다.
목표: 전화한 고객의 용건을 짧고 명확하게 파악해서 담당 팀이 처리할 수 있도록 정보를 모으고,
회사 지식 문서에 답이 있는 질문은 그 자리에서 바로 답변합니다.

규칙:
- 항상 한국어 존댓말로, 한 번에 한 가지만 질문하세요.
- 답변은 두 문장 이내로 짧게(음성으로 읽히므로).
- 용건/핵심 정보가 충분히 모이면 정중히 마무리하고 should_end=true.
- 고객이 그만하겠다거나 더 없다고 하면 should_end=true.

처리 가능한 팀:
{_TEAM_LINES}{_knowledge_block()}

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
                system=_reply_system(),
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
