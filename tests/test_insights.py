"""분석(문의 유형 집계) 페이지 테스트."""
from fastapi.testclient import TestClient
from app.main import app
from app.database import session_scope
from app.models import Call, Ticket, Message

client = TestClient(app)


def _seed(sid, team_key, team_name, intent, title):
    with session_scope() as db:
        c = Call(call_sid=sid, from_number="0701", to_number="0705", status="completed", intent=intent)
        db.add(c); db.flush()
        db.add(Message(call_id=c.id, role="caller", text=title))
        db.add(Ticket(call_id=c.id, team_key=team_key, team_name=team_name,
                      title=title, summary=title, priority="normal", status="open"))


def test_insights_shows_distribution():
    _seed("INS_1","prodtech","생산기술팀","설비고장","1호기 고장")
    _seed("INS_2", "prodtech", "생산기술팀", "설비고장", "2호기 멈춤")
    _seed("INS_3", "quality", "양산품질팀", "불량", "불량 접수")
    r = client.get("/ui/insights")
    assert r.status_code == 200
    assert "생산기술팀" in r.text
    assert "팀(소관)별 분포" in r.text
    assert "설비고장" in r.text
    assert "AI로 문의 유형 자동 분류" in r.text


def test_insights_ai_suggest_no_key_graceful(monkeypatch):
    # LLM 미설정이면 제안이 비어도 페이지는 정상
    r = client.get("/ui/insights?suggest=1")
    assert r.status_code == 200
