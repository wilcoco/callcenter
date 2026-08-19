"""이메일 알림(SMTP) 로직 테스트 — 실제 발송 없이 순수 함수 검증."""
from app import mailer
from app.config import get_settings


def test_resolve_recipient_prefers_real_team_email(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "notify_email", "fallback@icams.co.kr")
    assert mailer.resolve_recipient("quality@icams.co.kr") == "quality@icams.co.kr"
    # 예시(placeholder) 주소는 무시하고 기본 수신처로
    assert mailer.resolve_recipient("production@example.com") == "fallback@icams.co.kr"
    assert mailer.resolve_recipient("") == "fallback@icams.co.kr"


def test_send_email_skipped_when_not_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "")
    assert mailer.send_email("x@icams.co.kr", "제목", "본문") is False


def test_send_email_skipped_without_recipient(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "mail.icams.co.kr")
    monkeypatch.setattr(s, "smtp_user", "callcenter@icams.co.kr")
    monkeypatch.setattr(s, "smtp_password", "x")
    assert mailer.send_email("", "제목", "본문") is False


def test_build_ticket_email_contains_key_fields():
    subject, body = mailer.build_ticket_email({
        "team_name": "양산품질팀",
        "title": "1호기 자동문 고장",
        "priority": "high",
        "caller_name": "생산팀 홍길동",
        "callback": "01012345678",
        "summary": "1호기 자동문이 고장남",
        "transcript": "고객: 자동문 고장이요\n상담원: 접수하겠습니다",
        "created_at": "2026-08-19 10:00",
        "dashboard_url": "https://x/ui/calls/1",
    })
    assert "양산품질팀" in subject and "1호기 자동문 고장" in subject
    assert "생산팀 홍길동" in body
    assert "01012345678" in body
    assert "높음" in body  # priority label
    assert "통화 전문" in body
    assert "https://x/ui/calls/1" in body


def test_team_email_edit_via_web():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import session_scope
    from app.models import Team

    client = TestClient(app)
    with session_scope() as db:
        tid = db.query(Team).filter_by(key="quality").first().id
    r = client.post(f"/ui/teams/{tid}/email", data={"email": "quality@icams.co.kr"},
                    follow_redirects=False)
    assert r.status_code == 303
    with session_scope() as db:
        assert db.get(Team, tid).email == "quality@icams.co.kr"
