"""지식 문서(knowledge/ 폴더) 로딩·프롬프트 주입 테스트."""
import app.llm as llm
from app.config import get_settings


def _set_paths(monkeypatch, file_path: str = "", dir_path: str = ""):
    settings = get_settings()
    monkeypatch.setattr(settings, "knowledge_file", file_path)
    monkeypatch.setattr(settings, "knowledge_dir", dir_path)


def test_knowledge_loaded_into_reply_prompt(tmp_path, monkeypatch):
    kb = tmp_path / "faq.md"
    kb.write_text("환불은 결제 후 7일 이내 전액 가능합니다.", encoding="utf-8")
    _set_paths(monkeypatch, dir_path=str(tmp_path))

    system = llm._reply_system()
    assert "환불은 결제 후 7일 이내" in system
    assert "회사_지식_문서" in system


def test_directory_loads_multiple_files_sorted(tmp_path, monkeypatch):
    (tmp_path / "b_요금제.md").write_text("프로는 월 5만원", encoding="utf-8")
    (tmp_path / "a_영업시간.txt").write_text("평일 9시부터 6시", encoding="utf-8")
    (tmp_path / "ignore.pdf").write_text("무시되어야 함", encoding="utf-8")
    _set_paths(monkeypatch, dir_path=str(tmp_path))

    text = llm.load_knowledge()
    assert "[문서: a_영업시간.txt]" in text
    assert "[문서: b_요금제.md]" in text
    assert "무시되어야 함" not in text
    assert text.index("영업시간") < text.index("요금제")  # 파일명 순


def test_legacy_single_file_still_supported(tmp_path, monkeypatch):
    kb = tmp_path / "knowledge.md"
    kb.write_text("단일 파일 내용", encoding="utf-8")
    _set_paths(monkeypatch, file_path=str(kb))
    assert "단일 파일 내용" in llm.load_knowledge()


def test_missing_paths_are_ok(monkeypatch):
    _set_paths(monkeypatch, "/nonexistent/knowledge.md", "/nonexistent/dir")
    assert llm.load_knowledge() == ""
    system = llm._reply_system()
    assert "AI 전화 상담원" in system
    assert "회사_지식_문서" not in system


def test_oversized_knowledge_is_truncated(tmp_path, monkeypatch):
    (tmp_path / "big.md").write_text("가" * (llm._KNOWLEDGE_MAX_CHARS + 1000), encoding="utf-8")
    _set_paths(monkeypatch, dir_path=str(tmp_path))
    assert len(llm.load_knowledge()) == llm._KNOWLEDGE_MAX_CHARS


def test_repo_default_knowledge_dir_loads():
    # 저장소에 포함된 기본 knowledge/ 폴더가 읽히는지 확인
    text = llm.load_knowledge()
    assert "환불" in text
    assert "[문서: company.md]" in text
