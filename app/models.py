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
    # ----- 실무 팀 -----
    {
        "key": "production",
        "name": "생산팀",
        "description": "제품 생산, 제조 현장 운영, 생산 일정·작업 관련 문의.",
        "keywords": ["생산", "제조", "라인", "작업", "조립"],
        "email": "production@example.com",
    },
    {
        "key": "prodtech",
        "name": "생산기술팀",
        "description": "생산 설비·공정 기술, 설비 고장·트러블, 금형·치공구, 공정 개선.",
        "keywords": ["설비", "공정", "장비", "금형", "치공구", "고장"],
        "email": "prodtech@example.com",
    },
    {
        "key": "quality",
        "name": "양산품질팀",
        "description": "양산 제품 품질, 불량, 검사, 품질 클레임·반품 접수.",
        "keywords": ["품질", "불량", "검사", "클레임", "하자", "반품", "성적서"],
        "email": "quality@example.com",
    },
    {
        "key": "partner",
        "name": "상생협력팀",
        "description": "협력사·외주업체 관계, 신규 거래(업체) 등록, 상생 협력 문의.",
        "keywords": ["협력사", "외주", "납품업체", "거래등록", "업체등록", "하청"],
        "email": "partner@example.com",
    },
    {
        "key": "material",
        "name": "자재관리팀",
        "description": "자재·부품 재고, 입출고, 자재 납기 관련 문의.",
        "keywords": ["자재", "재고", "입고", "출고", "부품", "납기"],
        "email": "material@example.com",
    },
    {
        "key": "sales",
        "name": "영업관리팀",
        "description": "수주, 견적, 주문, 납품 일정, 고객 계약·가격 문의.",
        "keywords": ["견적", "주문", "수주", "납품", "계약", "가격", "구매", "영업"],
        "email": "sales@example.com",
    },
    {
        "key": "mgmt",
        "name": "경영관리팀",
        "description": "총무·인사·회계 실무, 세금계산서, 급여, 채용, 대금 결제·정산.",
        "keywords": ["총무", "인사", "회계", "세금계산서", "급여", "채용", "결제", "환불", "대금", "입금", "정산"],
        "email": "mgmt@example.com",
    },
    {
        "key": "it",
        "name": "전산팀",
        "description": "전산 시스템, ERP, PC·네트워크, 홈페이지·이메일 오류.",
        "keywords": ["전산", "시스템", "ERP", "컴퓨터", "네트워크", "홈페이지", "이메일", "오류", "접속", "로그인"],
        "email": "it@example.com",
    },
    {
        "key": "hampyeong",
        "name": "함평팀",
        "description": "함평 사업장(공장) 관련 업무 전반.",
        "keywords": ["함평"],
        "email": "hampyeong@example.com",
    },
    {
        "key": "escon",
        "name": "에스콘",
        "description": "에스콘 관련 업무 전반.",
        "keywords": ["에스콘"],
        "email": "escon@example.com",
    },
    {
        "key": "design",
        "name": "설계팀",
        "description": "제품 설계, 도면, 사양(스펙) 검토·변경.",
        "keywords": ["설계", "도면", "사양", "스펙"],
        "email": "design@example.com",
    },
    {
        "key": "rnd",
        "name": "개발팀",
        "description": "신제품 개발, 연구, 시제품·샘플 관련.",
        "keywords": ["개발", "신제품", "연구", "시제품", "샘플"],
        "email": "rnd@example.com",
    },
    # ----- 임원 (경영 판단이 필요한 중대 사안에만 배정) -----
    {
        "key": "exec_finance",
        "name": "회계담당임원",
        "description": "[임원] 회계·재무·자금 관련 중대 사안, 세무조사, 회계감사.",
        "keywords": ["세무조사", "회계감사", "자금"],
        "email": "exec.finance@example.com",
    },
    {
        "key": "exec_labor",
        "name": "노무담당임원",
        "description": "[임원] 노무·노사 문제, 산재, 임금 분쟁, 해고 등 인사 관련 중대 사안.",
        "keywords": ["노무", "노조", "산재", "임금체불", "해고", "노동청"],
        "email": "exec.labor@example.com",
    },
    {
        "key": "ceo_mgmt",
        "name": "관리각자대표",
        "description": "[대표] 관리부문 최고 책임자. 경영 전반의 최종 판단이 필요한 사안, 대표 면담 요청, 대외 중요 사안.",
        "keywords": [],
        "email": "ceo.mgmt@example.com",
    },
    {
        "key": "ceo_prod",
        "name": "생산각자대표",
        "description": "[대표] 생산부문 최고 책임자. 생산 부문 전체에 걸친 최종 판단이 필요한 사안.",
        "keywords": [],
        "email": "ceo.prod@example.com",
    },
    {
        "key": "exec_prod",
        "name": "생산담당임원",
        "description": "[임원] 생산 관련 중대 사안, 대형 생산 차질·전면 중단 등.",
        "keywords": [],
        "email": "exec.prod@example.com",
    },
    {
        "key": "exec_quality",
        "name": "품질담당임원",
        "description": "[임원] 대형 품질 사고, 리콜, 중대 클레임 등 품질 관련 중대 사안.",
        "keywords": ["리콜"],
        "email": "exec.quality@example.com",
    },
    {
        "key": "exec_rnd",
        "name": "연구개발담당임원",
        "description": "[임원] 연구개발 관련 중대 사안, 기술 제휴·특허 분쟁 등.",
        "keywords": ["기술제휴", "특허"],
        "email": "exec.rnd@example.com",
    },
    # ----- 기본값 -----
    {
        "key": "general",
        "name": "일반/대표창구",
        "description": "위 어디에도 해당하지 않거나 분류가 모호한 일반 문의 (기본값).",
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
    caller_name: Mapped[str] = mapped_column(String(128), default="")  # 문의자 (소속/이름)
    callback: Mapped[str] = mapped_column(String(64), default="")  # 회신 연락처
    priority: Mapped[str] = mapped_column(String(16), default="normal")  # low|normal|high|urgent
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    call: Mapped["Call"] = relationship(back_populates="ticket")


class GlossaryTerm(Base):
    """음성 인식 교정용 주요 단어 (설비명·제품명·약칭 등).

    term: 표준 단어 (예: 생산기술팀, 1호기, 사출기)
    aliases: 잘못 들리기 쉬운 발음/유사어 (쉼표 구분, 선택)
    note: 관리자용 메모 (선택)
    """

    __tablename__ = "glossary_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(128), index=True)
    aliases: Mapped[str] = mapped_column(String(255), default="")
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)


class KnowledgeDoc(Base):
    """웹 화면에서 등록하는 회사 지식 문서 (규정/FAQ 등).

    knowledge/ 폴더의 파일 문서와 함께 AI 응대 프롬프트에 포함된다.
    DB에 저장되므로 재배포와 무관하게 유지된다.
    """

    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


# 용어 사전 기본 단어 (표준단어, 유사발음, 메모) — 최초 1회만 시드
DEFAULT_GLOSSARY = [
    ("생산기술팀", "정수기술팀, 생기팀, 생산기수팀", "설비·공정 담당"),
    ("양산품질팀", "양품팀, 양산품질팁", "품질·불량·클레임"),
    ("자재관리팀", "자재팀", "자재·부품 납기"),
    ("경영관리팀", "경관팀", "총무·인사·회계"),
    ("상생협력팀", "협력팀", "협력사·외주"),
    ("영업관리팀", "영업팀", "수주·견적·납품"),
    ("사출", "사철", "플라스틱 사출 공정"),
    ("도장", "도색", "페인트 도장 공정"),
    ("조립", "조립라인", "조립 공정"),
    ("사출기", "사출기계, 사출 머신", ""),
    ("금형", "그금형", "사출 금형"),
    ("컨베이어", "컨베어, 콘베어", "이송 설비"),
    ("1호기", "일호기, 일오기", "설비 1호기"),
    ("2호기", "이호기, 이오기", "설비 2호기"),
    ("3호기", "삼호기", "설비 3호기"),
    ("불량", "불양, 부량", "품질 불량"),
    ("클레임", "클래임, 클레인", "품질 클레임"),
    ("성적서", "성작서", "품질 성적서"),
    ("납기", "남기", "자재/제품 납기"),
    ("견적", "겨적", ""),
    ("자재", "자제", "부품·원자재"),
    ("범퍼", "밤퍼", "자동차 범퍼"),
    ("크래시패드", "크래쉬패드", "자동차 내장 부품"),
    ("ERP", "이알피", "전산 시스템"),
    ("MES", "엠이에스", "생산관리 시스템"),
]


def seed_default_glossary(db: Session) -> None:
    """용어 사전이 완전히 비어있을 때만 기본 단어를 등록한다.

    (관리자가 지운 단어가 재시작 때 되살아나지 않도록 '비어있을 때만')
    """
    if db.query(GlossaryTerm).count() > 0:
        return
    for term, aliases, note in DEFAULT_GLOSSARY:
        db.add(GlossaryTerm(term=term, aliases=aliases, note=note))
    db.flush()


def seed_default_teams(db: Session) -> None:
    """DEFAULT_TEAMS 기준으로 teams 테이블 동기화 (추가/갱신/삭제).

    티켓은 team_key/team_name 사본을 갖고 있어 팀 삭제에도 안전하다.
    """
    specs = {t["key"]: t for t in DEFAULT_TEAMS}
    existing = {t.key: t for t in db.query(Team).all()}

    for key, spec in specs.items():
        if key in existing:
            row = existing[key]
            row.name = spec["name"]
            row.description = spec["description"]
            row.email = spec["email"]
        else:
            db.add(
                Team(
                    key=key,
                    name=spec["name"],
                    description=spec["description"],
                    email=spec["email"],
                )
            )
    for key, row in existing.items():
        if key not in specs:
            db.delete(row)
    db.flush()
