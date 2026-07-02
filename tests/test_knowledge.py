"""지식 문서(knowledge.md) 로딩·프롬프트 주입 테스트."""
import app.llm as llm
from app.config import get_settings


def _set_knowledge_file(monkeypatch, path: str):
    settings = get_settings()
    monkeypatch.setattr(settings, "knowledge_file", path)


def test_knowledge_loaded_into_reply_prompt(tmp_path, monkeypatch):
    kb = tmp_path / "knowledge.md"
    kb.write_text("환불은 결제 후 7일 이내 전액 가능합니다.", encoding="utf-8")
    _set_knowledge_file(monkeypatch, str(kb))

    system = llm._reply_system()
    assert "환불은 결제 후 7일 이내" in system
    assert "회사_지식_문서" in system


def test_missing_knowledge_file_is_ok(monkeypatch):
    _set_knowledge_file(monkeypatch, "/nonexistent/knowledge.md")
    assert llm.load_knowledge() == ""
    # 문서가 없어도 프롬프트는 정상 생성
    system = llm._reply_system()
    assert "AI 전화 상담원" in system
    assert "회사_지식_문서" not in system


def test_oversized_knowledge_is_truncated(tmp_path, monkeypatch):
    kb = tmp_path / "big.md"
    kb.write_text("가" * (llm._KNOWLEDGE_MAX_CHARS + 1000), encoding="utf-8")
    _set_knowledge_file(monkeypatch, str(kb))
    assert len(llm.load_knowledge()) == llm._KNOWLEDGE_MAX_CHARS


def test_repo_default_knowledge_file_loads():
    # 저장소에 포함된 기본 knowledge.md가 읽히는지 확인
    text = llm.load_knowledge()
    assert "환불" in text
