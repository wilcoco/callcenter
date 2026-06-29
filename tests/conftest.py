"""테스트 공통 설정: 임시 SQLite DB 사용."""
import os
import tempfile

import pytest

# 설정 캐시가 만들어지기 전에 환경변수로 임시 DB 지정
_tmp = tempfile.mkdtemp(prefix="callcenter-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ.setdefault("ANTHROPIC_API_KEY", "")  # 폴백(rule-based)으로 테스트


@pytest.fixture(scope="session", autouse=True)
def _init_db():
    from app.database import init_db

    init_db()
