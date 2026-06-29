"""DB 모델: 팀 / 통화 / 메시지 / 티켓."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from .database import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------------------
# 기본 팀 정의 — 라우팅(분류) 대상이자 시드 데이터
# ---------------------------------------------------------------------------
DEFAULT_TEAMS = [
    {
        "key": "support",
        "name": "고객지원팀",
        "description": "제품 사용 문의, 사용법 안내, 일반 고객 응대.",
        "keywords": ["사용법", "어떻게", "문의", "도와", "안내", "계정", "로그인"],
        "email": "support@example.com",
    },
    {
        "key": "billing",
        "name": "결제/청구팀",
        "description": "요금, 결제, 환불, 청구서, 구독 관련 문의.",
        "keywords": ["결제", "환불", "요금", "청구", "카드", "구독", "취소", "영수증"],
        "email": "billing@example.com",
    },
    {
        "key": "tech",
        "name": "기술지원팀",
        "description": "오류, 장애, 버그, 접속 불가 등 기술적 문제.",
        "keywords": ["오류", "에러", "장애", "버그", "안돼", "안 돼", "접속", "느려", "멈춰", "고장"],
        "email": "tech@example.com",
    },
    {
        "key": "sales",
        "name": "영업팀",
        "description": "신규 구매, 견적, 계약, 도입 상담.",
        "keywords": ["구매", "견적", "도입", "계약", "가격", "상담", "신규", "데모"],
        "email": "sales@example.com",
    },
    {
        "key": "general",
        "name": "일반/대표창구",
        "description": "분류가 모호하거나 기타 일반 문의 (기본값).",
        "keywords": [],
        "email": "hello@example.com",
    },
]


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    email: Mapped[str] = mapped_column(String(255), default="")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_sid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    from_number: Mapped[str] = mapped_column(String(32), default="")
    to_number: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(32), default="in-progress")
    turns: Mapped[int] = mapped_column(Integer, default=0)

    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    ended_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="call", cascade="all, delete-orphan", order_by="Message.id"
    )
    ticket: Mapped[Optional["Ticket"]] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )

    def transcript_text(self) -> str:
        lines = []
        for m in self.messages:
            who = "상담원" if m.role == "agent" else "고객"
            lines.append(f"{who}: {m.text}")
        return "\n".join(lines)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "caller" | "agent"
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    call: Mapped["Call"] = relationship(back_populates="messages")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id"), unique=True, index=True)
    team_key: Mapped[str] = mapped_column(String(32), index=True)
    team_name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="normal")  # low|normal|high|urgent
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    call: Mapped["Call"] = relationship(back_populates="ticket")


def seed_default_teams(db: Session) -> None:
    existing = {t.key for t in db.query(Team).all()}
    for spec in DEFAULT_TEAMS:
        if spec["key"] not in existing:
            db.add(
                Team(
                    key=spec["key"],
                    name=spec["name"],
                    description=spec["description"],
                    email=spec["email"],
                )
            )
    db.flush()
