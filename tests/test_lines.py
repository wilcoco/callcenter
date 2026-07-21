"""다회선(번호별 인사말/맥락) 기능 테스트."""
from fastapi.testclient import TestClient

from app import callbot
from app.main import app

client = TestClient(app)


def test_per_line_greeting_and_context_in_prompt():
    p = callbot.build_voice_system_prompt(
        greeting="안녕하세요, 캠스 채용문의입니다. 지원 관련 문의를 남겨 주세요.",
        context="이 번호는 채용 지원자 문의 전용입니다.",
    )
    assert "채용문의입니다" in p
    assert "채용 지원자 문의 전용" in p


def test_default_greeting_when_blank():
    p = callbot.build_voice_system_prompt(greeting="", context=None)
    assert callbot.DEFAULT_GREETING in p


def test_line_crud_via_web():
    r = client.post(
        "/ui/lines",
        data={
            "number": "07011112222",
            "name": "채용문의",
            "greeting": "안녕하세요, 캠스 채용문의입니다.",
            "context": "채용 지원자 문의 전용",
            "active": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "채용문의" in client.get("/ui/lines").text

    # active_line_profiles 에 반영
    lines = callbot.active_line_profiles()
    assert any(l["number"] == "07011112222" and l["greeting"] for l in lines)


def test_inactive_line_excluded():
    client.post(
        "/ui/lines",
        data={"number": "07099998888", "name": "중지선", "greeting": "", "context": "", "active": ""},
    )
    nums = {l["number"] for l in callbot.active_line_profiles()}
    assert "07099998888" not in nums


def test_line_delete():
    client.post("/ui/lines", data={"number": "07055556666", "name": "임시", "active": "1"})
    from app.database import session_scope
    from app.models import LineProfile

    with session_scope() as db:
        lid = db.query(LineProfile).filter_by(number="07055556666").first().id
    r = client.post(f"/ui/lines/{lid}/delete", follow_redirects=False)
    assert r.status_code == 303
    nums = {l["number"] for l in callbot.active_line_profiles()}
    assert "07055556666" not in nums
