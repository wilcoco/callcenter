"""웹 UI(메뉴/대시보드/티켓/통화) 테스트."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _make_call_with_ticket(sid: str) -> None:
    client.post("/voice/incoming", data={"CallSid": sid, "From": "+8210", "To": "+8225"})
    client.post("/voice/respond", data={"CallSid": sid, "SpeechResult": "환불 문의드립니다"})
    client.post("/voice/status", data={"CallSid": sid, "CallStatus": "completed"})


def test_dashboard_renders():
    r = client.get("/")
    assert r.status_code == 200
    assert "대시보드" in r.text
    assert "총 통화" in r.text


def test_tickets_page_lists_ticket_and_filters():
    _make_call_with_ticket("CA_UI_1")
    r = client.get("/ui/tickets")
    assert r.status_code == 200
    assert "환불" in r.text

    r = client.get("/ui/tickets", params={"team": "mgmt"})
    assert r.status_code == 200


def test_ticket_status_change():
    _make_call_with_ticket("CA_UI_2")
    tickets = client.get("/tickets").json()
    tid = tickets[0]["id"]

    r = client.post(f"/ui/tickets/{tid}/status", data={"status": "done"}, follow_redirects=False)
    assert r.status_code == 303

    assert client.get(f"/tickets/{tid}").json()["status"] == "done"


def test_ticket_team_reassignment():
    _make_call_with_ticket("CA_UI_TEAM")
    tid = client.get("/tickets").json()[0]["id"]

    r = client.post(f"/ui/tickets/{tid}/team", data={"team_key": "design"}, follow_redirects=False)
    assert r.status_code == 303

    t = client.get(f"/tickets/{tid}").json()
    assert t["team_key"] == "design"
    assert t["team_name"] == "설계팀"


def test_ticket_team_rejects_invalid():
    _make_call_with_ticket("CA_UI_TEAM2")
    tid = client.get("/tickets").json()[0]["id"]
    r = client.post(f"/ui/tickets/{tid}/team", data={"team_key": "no-such-team"})
    assert r.status_code == 400


def test_ticket_status_rejects_invalid():
    _make_call_with_ticket("CA_UI_3")
    tid = client.get("/tickets").json()[0]["id"]
    r = client.post(f"/ui/tickets/{tid}/status", data={"status": "hacked"})
    assert r.status_code == 400


def test_calls_page_and_detail_transcript():
    _make_call_with_ticket("CA_UI_4")
    r = client.get("/ui/calls")
    assert r.status_code == 200
    assert "통화 기록" in r.text

    calls = client.get("/calls").json()
    call = next(c for c in calls if c["call_sid"] == "CA_UI_4")
    r = client.get(f"/ui/calls/{call['id']}")
    assert r.status_code == 200
    assert "환불 문의드립니다" in r.text  # 대화 전문 표시
    assert "배정된 티켓" in r.text


def test_call_detail_404():
    assert client.get("/ui/calls/999999").status_code == 404
