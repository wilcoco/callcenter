"""SQLAlchemy 엔진/세션 구성."""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = get_settings().database_url
    # Railway 등 일부 서비스는 postgres:// 접두사를 쓰는데 SQLAlchemy 2는
    # postgresql:// 만 인식하므로 정규화
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    # SQLite 파일 디렉터리 생성
    if url.startswith("sqlite:///") and "./" in url:
        path = url.replace("sqlite:///", "", 1)
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    """테이블 생성 + 경량 마이그레이션 + 기본 팀 시드."""
    from . import models  # noqa: F401  (모델 등록)

    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    with session_scope() as db:
        models.seed_default_teams(db)
        models.seed_default_glossary(db)


def _ensure_columns() -> None:
    """create_all은 기존 테이블에 컬럼을 추가하지 않으므로,
    새로 추가된 컬럼을 ALTER TABLE로 보강한다 (SQLite/Postgres 공통)."""
    from sqlalchemy import inspect, text

    required = {
        "tickets": {
            "caller_name": "VARCHAR(128) DEFAULT ''",
            "callback": "VARCHAR(64) DEFAULT ''",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in required.items():
            if table not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI 의존성."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
