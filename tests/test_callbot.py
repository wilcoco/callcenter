"""ClawOps 음성봇 연동(이벤트 → DB → 티켓) 테스트. SDK 연결 없이 순수 함수만 검증."""
from app import callbot
from app.config import get_settings
from app.database import session_scope
from app.models import Call


def _get_call(call_id: str):
    with session_scope() as db:
        call = db.query(Call).filter_by(call_sid=call_id).one()
        # 세션 밖에서 쓸 값들을 미리 로드
        _ = call.transcript_text(), call.ticket
        return call


def test_full_call_flow_creates_ticket():
    cid = "CO_TEST_1"
    callbot.record_call_start(cid, "07011112222", "07099998888")
    callbot.record_transcript(cid, "assistant", "안녕하세요, 무엇을 도와드릴까요?")
    callbot.record_transcript(cid, "user", "납품받은 부품에 불량이 있어서 클레임 접수하려고요")
    callbot.record_transcript(cid, "assistant", "확인했습니다. 담당 부서에 전달하겠습니다.")
    callbot.record_call_end(cid)

    call = _get_call(cid)
    assert call.status == "completed"
    assert "클레임" in call.transcript_text()
    assert call.ticket is not None
    assert call.ticket.team_key == "quality"  # 불량/클레임 → 양산품질팀


def test_call_end_is_idempotent():
    cid = "CO_TEST_2"
    callbot.record_call_start(cid, "0701", "0702")
    callbot.record_transcript(cid, "user", "견적 문의드립니다")
    callbot.record_call_end(cid)
    callbot.record_call_end(cid)  # 중복 호출

    call = _get_call(cid)
    assert call.ticket is not None


def test_empty_transcript_is_skipped():
    cid = "CO_TEST_3"
    callbot.record_call_start(cid, "0701", "0702")
    callbot.record_transcript(cid, "user", "   ")
    call = _get_call(cid)
    assert call.transcript_text() == ""


def test_unknown_call_end_does_not_crash():
    callbot.record_call_end("CO_NEVER_STARTED")


def test_voice_prompt_contains_teams_and_knowledge():
    prompt = callbot.build_voice_system_prompt()
    assert "양산품질팀" in prompt
    assert "hang_up" in prompt
    assert "회사_지식_문서" in prompt  # 저장소 기본 knowledge/ 문서 포함


def test_clawops_disabled_without_keys(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "clawops_api_key", "")
    assert callbot.clawops_enabled() is False
    monkeypatch.setattr(s, "clawops_api_key", "sk_x")
    monkeypatch.setattr(s, "clawops_account_id", "AC_x")
    monkeypatch.setattr(s, "clawops_from_number", "07012345678")
    assert callbot.clawops_enabled() is True
