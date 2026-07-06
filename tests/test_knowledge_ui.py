"""웹 지식 문서 메뉴(등록/수정/삭제 → AI 프롬프트 반영) 테스트."""
from fastapi.testclient import TestClient

from app import llm
from app.main import app

client = TestClient(app)


def test_create_doc_appears_in_knowledge_and_prompt():
    r = client.post(
        "/ui/knowledge",
        data={"title": "휴가규정테스트", "content": "연차는 입사일 기준 15일 부여된다."},
        follow_redirects=False,
    )
    assert r.status_code == 303

    text = llm.load_knowledge()
    assert "[문서: 휴가규정테스트]" in text
    assert "연차는 입사일 기준 15일" in text

    # 목록 페이지에도 표시
    page = client.get("/ui/knowledge")
    assert "휴가규정테스트" in page.text


def test_edit_doc_updates_content():
    client.post("/ui/knowledge", data={"title": "경비규정", "content": "구버전"})
    docs_page = client.get("/ui/knowledge").text
    # id 추출 대신 API로 확인 어려우므로 DB에서 직접
    from app.database import session_scope
    from app.models import KnowledgeDoc

    with session_scope() as db:
        doc = db.query(KnowledgeDoc).filter_by(title="경비규정").first()
        doc_id = doc.id

    r = client.post(
        f"/ui/knowledge/{doc_id}",
        data={"title": "경비규정", "content": "법인카드는 사전 승인 후 사용한다."},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "법인카드는 사전 승인" in llm.load_knowledge()
    assert "구버전" not in llm.load_knowledge()


def test_delete_doc_removes_from_knowledge():
    client.post("/ui/knowledge", data={"title": "삭제될문서", "content": "임시 내용입니다"})
    from app.database import session_scope
    from app.models import KnowledgeDoc

    with session_scope() as db:
        doc_id = db.query(KnowledgeDoc).filter_by(title="삭제될문서").first().id

    r = client.post(f"/ui/knowledge/{doc_id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert "삭제될문서" not in llm.load_knowledge()


def test_edit_page_404_for_missing():
    assert client.get("/ui/knowledge/999999").status_code == 404
