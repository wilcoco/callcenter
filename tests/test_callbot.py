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
    assert "연락처" in prompt  # 회신 연락처 수집 지침
    assert "누구신지" in prompt  # 문의자 확인 지침
    assert "주식회사 캠스입니다" in prompt  # 내외부 공용 인사말


def test_ticket_stores_callback_from_transcript():
    cid = "CO_CONTACT_1"
    callbot.record_call_start(cid, "07011110000", "0705")
    callbot.record_transcript(cid, "user", "부품 견적 문의드립니다. 제 번호는 010-1234-5678 입니다")
    callbot.record_call_end(cid)
    call = _get_call(cid)
    assert call.ticket.callback == "01012345678"  # 정규화된 번호


def test_ticket_falls_back_to_caller_id():
    cid = "CO_CONTACT_2"
    callbot.record_call_start(cid, "07099998888", "0705")
    callbot.record_transcript(cid, "user", "자재 입고 일정 확인 부탁드립니다")
    callbot.record_call_end(cid)
    call = _get_call(cid)
    assert call.ticket.callback == "07099998888"  # 발신번호로 대체


def test_clawops_webhook_finalizes_missed_call():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    cid = "CO_WEBHOOK_1"
    callbot.record_call_start(cid, "0701", "0702")
    callbot.record_transcript(cid, "user", "설비가 고장나서 공정이 멈췄어요")
    # 에이전트가 call_end를 놓친 상황 → webhook이 마무리
    r = client.post("/clawops/webhook", data={"CallId": cid, "CallStatus": "completed"})
    assert r.status_code == 200

    call = _get_call(cid)
    assert call.ticket is not None
    assert call.ticket.team_key == "prodtech"  # 설비/고장/공정 → 생산기술팀


def test_clawops_webhook_json_event_finalizes():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    cid = "CO_WEBHOOK_JSON"
    callbot.record_call_start(cid, "0701", "0702")
    callbot.record_transcript(cid, "user", "자재 입고 일정 문의드립니다")
    # 콘솔 webhook 형식: JSON + event 필드
    r = client.post(
        "/clawops/webhook",
        json={"event": "transcript.completed", "data": {"call_id": cid}},
    )
    assert r.status_code == 200
    call = _get_call(cid)
    assert call.ticket is not None
    assert call.ticket.team_key == "material"  # 자재/입고 → 자재관리팀


def test_voicemail_fallback_returns_twiml():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post(
        "/clawops/voice",
        data={"CallId": "CO_VM_1", "From": "+8210", "To": "07052753895"},
    )
    assert r.status_code == 200
    assert "xml" in r.headers["content-type"]
    assert "<Record" in r.text
    assert "캠스" in r.text
    # 통화 레코드가 미리 생성됨
    call = _get_call("CO_VM_1")
    assert call is not None


def test_voicemail_transcript_webhook_creates_ticket():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    cid = "CO_VM_2"
    client.post("/clawops/voice", data={"CallId": cid, "From": "+8210"})
    # 녹음 전사 완료 이벤트 (segments 포함)
    r = client.post(
        "/clawops/webhook",
        json={
            "event": "transcript.completed",
            "data": {
                "call_id": cid,
                "segments": [
                    {"speaker": "AGENT", "start": 0, "end": 3, "text": "삐 소리 후 남겨주세요"},
                    {"speaker": "CUSTOMER", "start": 4, "end": 9,
                     "text": "설계팀에 전달해주세요. 도면 검토 요청입니다"},
                ],
            },
        },
    )
    assert r.status_code == 200
    call = _get_call(cid)
    assert "도면 검토" in call.transcript_text()
    assert call.ticket is not None
    assert call.ticket.team_key == "design"  # 설계팀 직접 지정


def test_ingest_skips_when_live_messages_exist():
    cid = "CO_VM_3"
    callbot.record_call_start(cid, "0701", "0702")
    callbot.record_transcript(cid, "user", "실시간으로 기록된 발화")
    stored = callbot.ingest_transcript_segments(
        cid, [{"speaker": "CUSTOMER", "text": "전사 중복 저장되면 안 됨"}]
    )
    assert stored is False
    assert "전사 중복" not in _get_call(cid).transcript_text()


def test_clawops_webhook_signature_rejected(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app

    s = get_settings()
    monkeypatch.setattr(s, "clawops_signing_key", "test_key")
    client = TestClient(app)
    r = client.post("/clawops/webhook", data={"CallId": "CO_X", "CallStatus": "completed"})
    assert r.status_code == 403  # 서명 없음 → 거부


def test_session_type_selection(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "clawops_session", "")
    monkeypatch.setattr(s, "openai_api_key", "")
    assert callbot.pick_session_type() == "pipeline"
    monkeypatch.setattr(s, "openai_api_key", "sk-xxx")
    assert callbot.pick_session_type() == "realtime"
    monkeypatch.setattr(s, "clawops_session", "pipeline")
    assert callbot.pick_session_type() == "pipeline"  # 강제 지정 우선


def test_clawops_disabled_without_keys(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "clawops_api_key", "")
    assert callbot.clawops_enabled() is False
    monkeypatch.setattr(s, "clawops_api_key", "sk_x")
    monkeypatch.setattr(s, "clawops_account_id", "AC_x")
    monkeypatch.setattr(s, "clawops_from_number", "07012345678")
    assert callbot.clawops_enabled() is True
