"""접수 경로 페이지 테스트."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_routing_page_lists_general_first_and_recipients():
    r = client.get("/ui/routing")
    assert r.status_code == 200
    assert "회사 일반 문의" in r.text
    # 시드된 팀원이 수신자로 표시
    assert "생산기술팀" in r.text
    assert "icams.co.kr" in r.text
    assert "접수 경로" in r.text
