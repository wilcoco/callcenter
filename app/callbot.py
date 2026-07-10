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


def _glossary_block() -> str:
    """음성 인식 교정용 회사 고유명사 목록.

    팀/임원 이름은 자동 포함하고, knowledge에 '용어집' 문서가 있으면 그 내용도 넣는다.
    발음이 비슷하게 잘못 들려도 이 목록의 단어로 해석하도록 모델에 지시한다.
    """
    team_names = ", ".join(t["name"] for t in DEFAULT_TEAMS)

    term_lines: list[str] = []
    extra = ""
    try:
        from .database import session_scope
        from .models import GlossaryTerm, KnowledgeDoc

        with session_scope() as db:
            # 웹 "용어 사전" 메뉴에서 등록한 단어
            for t in db.query(GlossaryTerm).order_by(GlossaryTerm.term).all():
                term = (t.term or "").strip()
                if not term:
                    continue
                aliases = (t.aliases or "").strip()
                term_lines.append(f"{term} (유사발음: {aliases})" if aliases else term)
            # (하위호환) 제목에 '용어'가 든 지식 문서도 포함
            docs = db.query(KnowledgeDoc).filter(KnowledgeDoc.title.like("%용어%")).all()
            extra = "\n".join((d.content or "").strip() for d in docs if (d.content or "").strip())
    except Exception:  # pragma: no cover
        pass

    body = f"부서/직책 이름: {team_names}"
    if term_lines:
        body += "\n주요 단어: " + ", ".join(term_lines)
    if extra:
        body += f"\n{extra}"

    return f"""

[회사 고유명사 — 음성 인식 교정용]
아래는 이 회사에서 자주 쓰는 고유명사입니다. 고객 발화가 발음이 비슷한 다른 단어로
들리더라도(예: '생산기술팀'을 '정수기술팀'으로, '1호기'를 '일오기'로), 문맥상 아래
목록의 단어일 가능성이 높으면 그 단어로 해석하고, 애매하면 되물어 확인하세요.
{body}"""


def _company_context_block() -> str:
    ctx = get_settings().company_context.strip()
    if not ctx:
        return ""
    return f"""

[회사 소개 — 대화 맥락]
{ctx}
전화 건 분의 발화를 이 업종 맥락에서 이해하세요. 발음이 불분명해도 제조 현장에서
쓰일 법한 단어를 우선 고려하고, 일상 단어로 잘못 해석하지 마세요."""


def build_voice_system_prompt() -> str:
    """실시간 음성 대화용 시스템 프롬프트 (지식 문서 포함)."""
    return f"""당신은 주식회사 캠스의 안내전화 AI 상담원입니다. 지금 전화 건 사람과 실제 음성 통화 중입니다.
{_company_context_block()}
역할:
- 회사 대표 안내전화 AI입니다. 전화 건 분은 회사 구성원일 수도, 고객·협력사 등 외부인일 수도 있습니다.
- 문의 내용을 잘 듣고 정리해서 담당자가 회신할 수 있게 하는 것이 목표입니다.
- 조직 구조를 모를 수 있으므로 어느 팀 소관인지 절대 먼저 묻지 마세요.
  담당 배정은 통화가 끝난 뒤 시스템이 자동으로 합니다.
- 전화 건 분이 스스로 특정 팀이나 임원을 지정하면 그대로 접수합니다.
- 회사 지식 문서에 답이 있는 질문은 그 자리에서 바로 답변합니다.

[내부 정보 보호 — 반드시 지킬 것]
- '총무 업무 담당자' 자료의 담당자 이름·개인 휴대폰번호는 캠스 내부 정보입니다.
- 이 정보는 전화 건 분이 캠스 직원임을 밝힌 경우에만 안내하세요.
  먼저 소속과 성함을 확인하고, 외부인(고객·거래처)이거나 신원이 불분명하면
  개인 연락처 대신 "담당 부서로 접수해 회신드리겠다"고만 안내하세요.
- 업체(외부 협력사) 전화번호는 안내해도 무방합니다.

접수 절차:
1. 문의 내용을 듣습니다. 모호하면 한 가지씩 질문해서 구체화합니다 (무엇을, 언제까지, 왜).
2. 반드시 누구신지 여쭤봅니다. 예: "실례지만 어디의 누구신지 말씀해 주시겠어요?"
   (회사/소속과 성함. 구성원이면 팀과 성함.)
3. 회신 연락처 확인: get_caller_number 도구로 발신번호를 조회한 뒤, 번호를 또박또박
   불러주며 확인합니다. 예: "지금 010 1234 5678 번으로 전화 주셨네요. 이 번호로 회신드리면 될까요?"
   - "예/네" → 그대로 접수하고 넘어갑니다 (번호를 다시 묻지 않음).
   - 아니라고 하거나 다른 번호를 원하면 → 그 번호를 듣고 반드시 한 번 복창해서 확인합니다.
   - 도구가 unknown을 반환하면(번호 표시제한) "회신받으실 연락처를 말씀해 주시겠어요?"라고 직접 여쭤봅니다.
4. 종료 전 최종 확인 (반드시 지킬 것):
   a) 접수한 내용을 다시 정리해서 들려줍니다. 이름/소속, 용건(무엇을·어디서·언제까지),
      회신 연락처를 모두 포함해 또박또박 말합니다.
      예: "정리해 드리면, OO의 홍길동 님께서 1호기 자동문 고장 건으로 문의 주셨고,
           회신은 010 1234 5678 번으로 드리면 되는 것으로 접수하겠습니다. 맞으실까요?"
   b) 고객이 틀린 부분을 지적하면 그 부분을 고치고, 고친 내용을 다시 한 번 들려주며
      "이제 맞으실까요?"라고 재확인합니다. 맞다고 할 때까지 이 과정을 반복합니다.
   c) 고객이 "맞다/네"라고 확인하면 그때 비로소 마무리 인사를 하고 종료합니다:
      "확인 감사합니다. 담당 팀에 접수해 빠르게 회신드리겠습니다.
       전화 주셔서 감사합니다. 좋은 하루 되세요."
   - 최종 확인(a) 없이, 또는 고객이 "맞다"고 하기 전에는 절대 hang_up 하지 마세요.

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
- 통화를 끝내기 전에 반드시 접수 내용(이름/소속·용건·회신처)을 다시 들려주고
  "맞으실까요?"라고 확인받으세요. 틀리면 정정하고 다시 확인합니다.
- 고객이 "맞다"고 확인한 뒤에만 마무리 인사를 하고 hang_up 하세요.
  최종 확인 없이 갑자기 끊지 마세요.

담당 부서(참고용 — 고객에게 나열하지 말 것):
{_TEAM_LINES}{_glossary_block()}{llm_mod._knowledge_block()}"""


# ---------------------------------------------------------------------------
# 활성 통화 발신번호 추적 — AI가 통화 중 get_caller_number 도구로 조회
# (단일 회선 전제. 동시 통화 시 가장 최근 통화의 번호가 반환될 수 있음)
# ---------------------------------------------------------------------------
_active_callers: dict[str, str] = {}


def set_active_caller(call_id: str, number: str) -> None:
    _active_callers[call_id] = number or ""


def clear_active_caller(call_id: str) -> None:
    _active_callers.pop(call_id, None)


def get_active_caller_number() -> str:
    if not _active_callers:
        return ""
    return list(_active_callers.values())[-1]


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

    import os as _os

    if not _os.environ.get("DEEPGRAM_API_KEY") or not _os.environ.get("ELEVENLABS_API_KEY"):
        log.error(
            "파이프라인 음성 세션이 선택됐지만 DEEPGRAM_API_KEY/ELEVENLABS_API_KEY가 "
            "없습니다. 이 상태에서는 전화가 오면 통화 연결이 거부되어 보이스메일로 "
            "넘어갑니다. OPENAI_API_KEY를 설정하면 키 1개로 Realtime 모드로 동작합니다."
        )

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
        set_active_caller(call.call_id, call.from_number)
        record_call_start(call.call_id, call.from_number, call.to_number)

    @agent.on("transcript")
    async def _on_transcript(call, role, text):
        record_transcript(call.call_id, role, text)

    @agent.on("call_end")
    async def _on_end(call):
        clear_active_caller(call.call_id)
        record_call_end(call.call_id)

    @agent.tool
    async def get_caller_number() -> str:
        """지금 통화 중인 발신자의 전화번호(콜러ID)를 조회합니다.
        회신 번호를 확인할 때 사용하세요. 번호 표시제한이면 unknown을 반환합니다."""
        number = get_active_caller_number()
        return number if number and number.lower() not in {"anonymous", "unknown", ""} else "unknown"

    return agent
