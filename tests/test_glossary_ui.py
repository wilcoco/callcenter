"""용어 사전 메뉴(등록/삭제 → 음성 프롬프트 반영) 테스트."""
from fastapi.testclient import TestClient

from app import callbot
from app.main import app

client = TestClient(app)


def test_add_term_appears_in_page_and_prompt():
    r = client.post(
        "/ui/glossary",
        data={"term": "사출기2호기", "aliases": "사출기 이호기, 사출이호", "note": "조립1라인"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    page = client.get("/ui/glossary")
    assert "사출기2호기" in page.text
    assert "사출기 이호기" in page.text

    prompt = callbot.build_voice_system_prompt()
    assert "사출기2호기" in prompt
    assert "유사발음: 사출기 이호기" in prompt


def test_delete_term_removes_from_prompt():
    client.post("/ui/glossary", data={"term": "삭제될설비", "aliases": "", "note": ""})
    from app.database import session_scope
    from app.models import GlossaryTerm

    with session_scope() as db:
        tid = db.query(GlossaryTerm).filter_by(term="삭제될설비").first().id

    r = client.post(f"/ui/glossary/{tid}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert "삭제될설비" not in callbot.build_voice_system_prompt()


def test_empty_term_ignored():
    before = client.get("/ui/glossary").text.count("<tr>")
    client.post("/ui/glossary", data={"term": "   ", "aliases": "", "note": ""})
    after = client.get("/ui/glossary").text.count("<tr>")
    assert after == before
