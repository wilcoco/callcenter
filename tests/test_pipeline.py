"""전체 통화 파이프라인(웹훅 -> 티켓)을 폴백 모드로 검증."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _run_call(sid: str, utterances: list[str]):
    client.post("/voice/incoming", data={"CallSid": sid, "From": "+8210", "To": "+8225"})
    for u in utterances:
        r = client.post("/voice/respond", data={"CallSid": sid, "SpeechResult": u})
        assert r.status_code == 200
        assert "<Response>" in r.text
        if "Hangup" in r.text:
            break
    client.post("/voice/status", data={"CallSid": sid, "CallStatus": "completed"})


def test_incoming_greets_and_gathers():
    r = client.post("/voice/incoming", data={"CallSid": "CA_T1", "From": "+8210", "To": "+8225"})
    assert r.status_code == 200
    assert "Gather" in r.text
    assert "도와드릴까요" in r.text


def test_billing_call_creates_billing_ticket():
    sid = "CA_BILL_1"
    _run_call(sid, ["결제가 두 번 돼서 환불 받고 싶어요", "카드로 결제했어요", "그게 다예요"])

    tickets = client.get("/tickets", params={"team": "billing"}).json()
    assert any(t["call_id"] for t in tickets)
    mine = [t for t in tickets if t["team_key"] == "billing"]
    assert mine, "billing 티켓이 생성되어야 함"
    assert mine[0]["status"] == "open"
    assert mine[0]["summary"]


def test_finalize_is_idempotent():
    sid = "CA_IDEM"
    _run_call(sid, ["오류가 나서 접속이 안돼요", "계속 그래요"])
    # status 콜백을 또 보내도 티켓이 중복 생성되면 안 됨
    client.post("/voice/status", data={"CallSid": sid, "CallStatus": "completed"})
    calls = client.get("/calls").json()
    call = next(c for c in calls if c["call_sid"] == sid)
    assert call["ticket"] is not None
    # 해당 call의 티켓이 정확히 1개
    all_tickets = client.get("/tickets").json()
    assert sum(1 for t in all_tickets if t["call_id"] == call["id"]) == 1


def test_empty_call_creates_no_ticket():
    sid = "CA_EMPTY"
    client.post("/voice/incoming", data={"CallSid": sid, "From": "+8210", "To": "+8225"})
    client.post("/voice/status", data={"CallSid": sid, "CallStatus": "no-answer"})
    calls = client.get("/calls").json()
    call = next(c for c in calls if c["call_sid"] == sid)
    assert call["ticket"] is None


def test_health_and_teams():
    assert client.get("/health").json()["status"] == "ok"
    teams = client.get("/teams").json()
    assert {t["key"] for t in teams} >= {"billing", "tech", "sales", "support", "general"}
