"""팀 배정 수정 → 학습 사례 저장 → 분석 프롬프트 반영 테스트."""
from fastapi.testclient import TestClient

from app import llm
from app.main import app
from app.database import session_scope
from app.models import Call, Ticket, Message, RoutingExample

client = TestClient(app)


def _make_ticket(sid: str, team_key: str, title: str, summary: str) -> int:
    with session_scope() as db:
        c = Call(call_sid=sid, from_number="0701", to_number="0705", status="completed")
        db.add(c); db.flush()
        db.add(Message(call_id=c.id, role="caller", text=summary))
        t = Ticket(call_id=c.id, team_key=team_key, team_name="일반/대표창구",
                   title=title, summary=summary, priority="normal", status="open")
        db.add(t); db.flush()
        return t.id


def test_team_change_records_learning_example():
    tid = _make_ticket("LRN_1", "general", "자동문 문의", "정문 자동문이 안 열립니다")
    r = client.post(f"/ui/tickets/{tid}/team", data={"team_key": "prodtech"}, follow_redirects=False)
    assert r.status_code == 303
    with session_scope() as db:
        ex = db.query(RoutingExample).filter_by(team_key="prodtech").all()
        assert any("자동문" in e.text for e in ex)


def test_learning_example_appears_in_analysis_prompt():
    # 위 사례가 저장된 상태에서, 비슷한 통화 전문이면 프롬프트에 사례가 들어감
    with session_scope() as db:
        if not db.query(RoutingExample).filter_by(team_key="prodtech").first():
            db.add(RoutingExample(text="정문 자동문이 안 열립니다", team_key="prodtech", team_name="생산기술팀"))
    system = llm._analyze_system("고객: 자동문이 또 고장났어요")
    assert "관리자 수정 학습 사례" in system
    assert "자동문" in system
    assert "prodtech" in system


def test_no_change_records_nothing():
    tid = _make_ticket("LRN_2", "quality", "불량 접수", "불량 발생")
    before = 0
    with session_scope() as db:
        before = db.query(RoutingExample).count()
    # 같은 팀으로 '변경'하면 학습 안 함
    client.post(f"/ui/tickets/{tid}/team", data={"team_key": "quality"})
    with session_scope() as db:
        assert db.query(RoutingExample).count() == before
