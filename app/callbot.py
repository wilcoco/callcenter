"""ClawOps 실시간 음성봇 연동.

국내 070 번호(ClawOps)로 걸려온 전화를 실시간 음성 대화로 응대한다.
- STT: Deepgram (한국어) / LLM: Claude / TTS: ElevenLabs
- 대화 내용은 기존 파이프라인과 동일하게 DB에 기록되고,
  통화 종료 시 분석 → 팀 배정 → 티켓 생성이 실행된다.

필요 환경변수: CLAWOPS_API_KEY, CLAWOPS_ACCOUNT_ID, CLAWOPS_FROM_NUMBER,
DEEPGRAM_API_KEY, ELEVENLABS_API_KEY, ANTHROPIC_API_KEY
"""
from __future__ import annotations

import datetime as dt
import logging

from . import llm as llm_mod
from . import services
from .config import get_settings
from .database import session_scope
from .models import DEFAULT_TEAMS, Call

log = logging.getLogger("callcenter.callbot")

_TEAM_LINES = "\n".join(f"- {t['name']}: {t['description']}" for t in DEFAULT_TEAMS)


def build_voice_system_prompt() -> str:
    """실시간 음성 대화용 시스템 프롬프트 (지식 문서 포함)."""
    return f"""당신은 주식회사 캠스의 안내전화 AI 상담원입니다. 지금 전화 건 사람과 실제 음성 통화 중입니다.

역할:
- 회사 대표 안내전화 AI입니다. 전화 건 분은 회사 구성원일 수도, 고객·협력사 등 외부인일 수도 있습니다.
- 문의 내용을 잘 듣고 정리해서 담당자가 회신할 수 있게 하는 것이 목표입니다.
- 조직 구조를 모를 수 있으므로 어느 팀 소관인지 절대 먼저 묻지 마세요.
  담당 배정은 통화가 끝난 뒤 시스템이 자동으로 합니다.
- 전화 건 분이 스스로 특정 팀이나 임원을 지정하면 그대로 접수합니다.
- 회사 지식 문서에 답이 있는 질문은 그 자리에서 바로 답변합니다.

접수 절차:
1. 문의 내용을 듣습니다. 모호하면 한 가지씩 질문해서 구체화합니다 (무엇을, 언제까지, 왜).
2. 반드시 누구신지 여쭤봅니다. 예: "실례지만 어디의 누구신지 말씀해 주시겠어요?"
   (회사/소속과 성함. 구성원이면 팀과 성함.)
3. 회신 연락처는 번호를 불러달라고 하지 말고, 먼저 이렇게 확인합니다:
   "회신은 지금 전화 주신 번호로 드리면 될까요?"
   - "예/네" → 그대로 접수하고 넘어갑니다 (번호를 다시 묻지 않음).
   - 다른 번호로 해달라고 하면 → 그 번호를 듣고 반드시 한 번 복창해서 확인합니다.
4. 마지막에 문의 내용을 한 문장으로 요약 복창하고
   "확인 후 빠르게 회신드리겠습니다. 감사합니다."라고 마무리합니다.

말하기 규칙:
- 한국어 존댓말. 음성으로 전달되므로 한 번에 1~2문장으로 짧게.
- 통화 시작 시 정확히 이렇게 인사: "안녕하세요, 주식회사 캠스입니다. 문의하실 내용을 말씀해 주시면 확인 후 회신드리겠습니다."
- 한 번에 한 가지만 질문하고, 목록 나열이나 특수기호는 쓰지 마세요.
- 숫자·전화번호는 또박또박 읽기 좋게 말하세요.
- 음성 인식이 불완전할 수 있습니다. 발화가 문맥상 어색하면 발음이 비슷한 단어로
  잘못 들렸을 가능성을 고려해 문맥으로 해석하고, 확신이 없으면 추측하지 말고
  "혹시 ~라고 말씀하신 게 맞을까요?"라고 정중히 확인하세요.
- 회사·제품 이름, 수량, 날짜 같은 중요한 정보는 한 번 복창해서 확인하세요.

종료 규칙:
- 용건과 핵심 정보(무엇을, 언제, 어떤 문제)가 충분히 모이면
  "담당 부서에 전달해 연락드리겠습니다"라고 정중히 마무리한 뒤 hang_up 도구로 통화를 종료하세요.
- 고객이 끊겠다고 하거나 더 없다고 하면 인사 후 hang_up 하세요.

담당 부서(참고용 — 고객에게 나열하지 말 것):
{_TEAM_LINES}{llm_mod._knowledge_block()}"""


# ---------------------------------------------------------------------------
# 통화 이벤트 → DB 기록 (ClawOps SDK와 분리된 순수 함수 — 테스트 용이)
# ---------------------------------------------------------------------------
def record_call_start(call_id: str, from_number: str, to_number: str) -> None:
    with session_scope() as db:
        services.get_or_create_call(db, call_id, from_number=from_number, to_number=to_number)
    log.info("통화 시작: %s (from %s)", call_id, from_number)


def record_transcript(call_id: str, role: str, text: str) -> None:
    """role: 'user'(고객) | 'assistant'(상담원)"""
    mapped = "caller" if role == "user" else "agent"
    if not text.strip():
        return
    with session_scope() as db:
        call = services.get_or_create_call(db, call_id)
        services.add_message(db, call, mapped, text.strip())


def ingest_transcript_segments(
    call_id: str, segments: list[dict], from_number: str = "", to_number: str = ""
) -> bool:
    """서버 전사(segments)를 통화 기록으로 저장.

    보이스메일(fallback)로 남긴 통화처럼 실시간 기록이 없는 경우에 사용.
    이미 대화가 기록된 통화면 중복 저장하지 않는다.
    segments: [{"speaker": "CUSTOMER"|"AGENT", "text": "..."}]
    반환: 새로 저장했으면 True.
    """
    with session_scope() as db:
        call = services.get_or_create_call(db, call_id, from_number=from_number, to_number=to_number)
        if call.messages:
            return False
        stored = False
        for seg in segments:
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            role = "caller" if str(seg.get("speaker", "CUSTOMER")).upper() == "CUSTOMER" else "agent"
            services.add_message(db, call, role, text)
            stored = True
        return stored


def fetch_transcript_segments(call_id: str) -> list[dict]:
    """ClawOps API에서 통화 전사를 조회. 실패/미완료 시 빈 리스트."""
    s = get_settings()
    if not (s.clawops_api_key and s.clawops_account_id):
        return []
    try:
        from clawops import ClawOps

        client = ClawOps(api_key=s.clawops_api_key, account_id=s.clawops_account_id)
        ts = client.calls.get_transcript(call_id)
        if ts.status == "completed" and ts.segments:
            return [{"speaker": seg.speaker, "text": seg.text} for seg in ts.segments]
        log.info("전사 미완료(call=%s, status=%s)", call_id, ts.status)
    except Exception as exc:
        log.warning("전사 조회 실패(call=%s): %s", call_id, exc)
    return []


def record_call_end(call_id: str) -> None:
    """통화 종료 → 분석 + 팀 배정 + 티켓 생성 (멱등)."""
    with session_scope() as db:
        call = db.query(Call).filter_by(call_sid=call_id).one_or_none()
        if call is None:
            log.warning("종료 이벤트를 받았지만 통화 기록이 없음: %s", call_id)
            return
        call.ended_at = call.ended_at or dt.datetime.now(dt.timezone.utc)
        ticket = services.finalize_call(db, call)
    if ticket is not None:
        log.info("통화 %s 종료 → 티켓 #%s [%s]", call_id, ticket.id, ticket.team_name)


# ---------------------------------------------------------------------------
# ClawOps 에이전트 구성
# ---------------------------------------------------------------------------
def clawops_enabled() -> bool:
    s = get_settings()
    return bool(s.clawops_api_key and s.clawops_account_id and s.clawops_from_number)


def pick_session_type() -> str:
    """사용할 음성 세션 방식을 결정.

    - openai_api_key 가 있으면 'realtime' (OpenAI Realtime — 키 1개로 STT/LLM/TTS 모두 처리)
    - deepgram+elevenlabs 키가 있으면 'pipeline' (Deepgram STT + Claude + ElevenLabs TTS)
    - CLAWOPS_SESSION 환경변수로 강제 지정 가능
    """
    s = get_settings()
    if s.clawops_session in {"realtime", "pipeline"}:
        return s.clawops_session
    if s.openai_api_key:
        return "realtime"
    return "pipeline"


def _build_session():
    s = get_settings()
    prompt = build_voice_system_prompt()

    if pick_session_type() == "realtime":
        from clawops.agent import OpenAIRealtime

        return OpenAIRealtime(
            api_key=s.openai_api_key or None,
            system_prompt=prompt,
            model=s.openai_realtime_model,
            voice=s.openai_realtime_voice,
            language="ko",
            greeting=True,
        )

    from clawops.agent.pipeline import AnthropicLLM, DeepgramSTT, ElevenLabsTTS, PipelineSession

    return PipelineSession(
        stt=DeepgramSTT(model=s.deepgram_model, language="ko"),
        llm=AnthropicLLM(model=s.reply_model, temperature=0.6, max_tokens=1024),
        tts=ElevenLabsTTS(voice_id=s.elevenlabs_voice_id, language_code="ko"),
        system_prompt=prompt,
        greeting=True,
        language="ko",
    )


def build_agent():
    """ClawOpsAgent 생성 (clawops_enabled() 확인 후 호출할 것)."""
    from clawops.agent import ClawOpsAgent

    s = get_settings()
    agent = ClawOpsAgent(
        api_key=s.clawops_api_key,
        account_id=s.clawops_account_id,
        from_=s.clawops_from_number,
        session=_build_session(),
    )

    @agent.on("call_start")
    async def _on_start(call):
        record_call_start(call.call_id, call.from_number, call.to_number)

    @agent.on("transcript")
    async def _on_transcript(call, role, text):
        record_transcript(call.call_id, role, text)

    @agent.on("call_end")
    async def _on_end(call):
        record_call_end(call.call_id)

    return agent
