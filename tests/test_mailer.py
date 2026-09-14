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


def test_collect_recipients_includes_always_team_and_contacts(monkeypatch):
    from app import services
    from app.config import get_settings
    from app.database import session_scope
    from app.models import Contact, Team

    s = get_settings()
    monkeypatch.setattr(s, "always_email", "json@icams.co.kr")
    monkeypatch.setattr(s, "notify_email", "")

    with session_scope() as db:
        team = db.query(Team).filter_by(key="quality").first()
        team.email = "quality-inbox@icams.co.kr"
        db.add(Contact(name="김담당", email="kim@icams.co.kr", team_key="quality", active=True))
        db.add(Contact(name="전체관리", email="all@icams.co.kr", team_key="", active=True))
        db.add(Contact(name="딴팀", email="other@icams.co.kr", team_key="sales", active=True))
    # 커밋 후(별개 트랜잭션) 수신자 조회
    with session_scope() as db:
        team_obj = db.query(Team).filter_by(key="quality").first()
        rec = services.collect_recipients("quality", team_obj)

    assert "json@icams.co.kr" in rec        # 항상
    assert "quality-inbox@icams.co.kr" in rec  # 팀
    assert "kim@icams.co.kr" in rec         # 팀 담당자
    assert "all@icams.co.kr" in rec         # 전체 담당자
    assert "other@icams.co.kr" not in rec   # 다른 팀 담당자 제외


def test_send_email_accepts_list(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "smtp_host", "")  # 미설정이라 실제 발송 안 함
    # 리스트/쉼표 문자열 모두 정규화되는지
    assert mailer._normalize_recipients(["a@x.com", "a@x.com", "b@y.com", "bad"]) == ["a@x.com", "b@y.com"]
    assert mailer._normalize_recipients("a@x.com, b@y.com") == ["a@x.com", "b@y.com"]


def test_directory_seeded_and_resolves_email():
    from app.database import session_scope
    from app.models import DirectoryPerson

    with session_scope() as db:
        p = db.query(DirectoryPerson).filter_by(login_id="afero").first()
        assert p is not None
        assert p.name == "오명진"
        assert p.email == "afero@icams.co.kr"
        # 대표전화 계정도 포함
        assert db.query(DirectoryPerson).filter_by(login_id="callcenter").first().name == "대표전화"


def test_ticket_assign_learns_team_contacts():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import session_scope
    from app.models import Call, Ticket, Contact, Message

    client = TestClient(app)
    # 통화+티켓 하나 생성
    with session_scope() as db:
        c = Call(call_sid="ASSIGN_1", from_number="0701", to_number="0705", status="completed")
        db.add(c); db.flush()
        db.add(Message(call_id=c.id, role="caller", text="설비 문제"))
        t = Ticket(call_id=c.id, team_key="prodtech", team_name="생산기술팀",
                   title="설비 점검", summary="설비 점검 요청", priority="normal", status="open")
        db.add(t); db.flush()
        tid = t.id

    # afero(오명진) 이메일로 지정
    r = client.post(f"/ui/tickets/{tid}/assign",
                    data={"emails": ["afero@icams.co.kr"]}, follow_redirects=False)
    assert r.status_code == 303
    # 학습: prodtech 팀 담당자로 등록됐는지
    with session_scope() as db:
        cc = db.query(Contact).filter_by(team_key="prodtech", email="afero@icams.co.kr").first()
        assert cc is not None
        assert cc.name == "오명진"
