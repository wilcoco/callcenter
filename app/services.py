"""통화/메시지/티켓 관련 도메인 서비스 (DB 조작 + 분석 연결)."""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.orm import Session

from . import llm
from .models import Call, Message, Team, Ticket

log = logging.getLogger(__name__)


def get_or_create_call(
    db: Session, call_sid: str, from_number: str = "", to_number: str = ""
) -> Call:
    call = db.query(Call).filter_by(call_sid=call_sid).one_or_none()
    if call is None:
        call = Call(
            call_sid=call_sid,
            from_number=from_number,
            to_number=to_number,
            status="in-progress",
        )
        db.add(call)
        db.flush()
    return call


def add_message(db: Session, call: Call, role: str, text: str) -> Message:
    msg = Message(call_id=call.id, role=role, text=text)
    db.add(msg)
    if role == "caller":
        call.turns += 1
    db.flush()
    return msg


def team_for_key(db: Session, key: str) -> Team | None:
    return db.query(Team).filter_by(key=key).one_or_none()


def finalize_call(db: Session, call: Call) -> Ticket | None:
    """통화 종료 시: 전문 분석 -> 요약/팀 배정 -> 티켓 생성(멱등).

    이미 티켓이 있으면 그대로 반환.
    """
    if call.ticket is not None:
        return call.ticket

    call.status = "completed"
    if call.ended_at is None:
        call.ended_at = dt.datetime.now(dt.timezone.utc)

    transcript = call.transcript_text()
    if not transcript.strip():
        log.info("call %s: 대화 내용 없음, 티켓 생략", call.call_sid)
        db.flush()
        return None

    analysis = llm.analyze_call(transcript)
    call.summary = analysis["summary"]
    call.intent = analysis["intent"]

    team = team_for_key(db, analysis["team_key"])
    team_name = team.name if team else analysis["team_key"]

    ticket = Ticket(
        call_id=call.id,
        team_key=analysis["team_key"],
        team_name=team_name,
        title=analysis["title"],
        summary=analysis["summary"],
        caller_name=analysis.get("caller_name", ""),
        # 통화 중 연락처를 안 남겼으면 발신번호로 회신
        callback=analysis.get("callback", "") or call.from_number,
        priority=analysis["priority"],
        status="open",
    )
    db.add(ticket)
    db.flush()
    log.info(
        "call %s -> 티켓 #%s [%s/%s] %s",
        call.call_sid, ticket.id, ticket.team_key, ticket.priority, ticket.title,
    )
    _notify_team_email(ticket, team, call)
    return ticket


def _notify_team_email(ticket: Ticket, team, call: Call) -> None:
    """담당 팀 이메일로 접수 알림 발송 (best-effort, 실패해도 무시)."""
    from .config import get_settings
    from . import mailer

    settings = get_settings()
    if not settings.email_enabled:
        return
    recipient = mailer.resolve_recipient(team.email if team else "")
    if not recipient:
        log.info("이메일 수신처 없음(팀/기본 모두 미설정) — 발송 생략")
        return

    base = settings.public_base_url.rstrip("/")
    info = {
        "team_name": ticket.team_name,
        "title": ticket.title,
        "priority": ticket.priority,
        "caller_name": ticket.caller_name,
        "callback": ticket.callback,
        "summary": ticket.summary,
        "transcript": call.transcript_text(),
        "call_id": call.id,
        "created_at": ticket.created_at.strftime("%Y-%m-%d %H:%M") if ticket.created_at else "",
        "dashboard_url": f"{base}/ui/calls/{call.id}" if base else "",
    }
    subject, body = mailer.build_ticket_email(info)
    # 통화 종료 처리를 막지 않도록 발송은 백그라운드 스레드에서
    import threading

    threading.Thread(
        target=mailer.send_email, args=(recipient, subject, body), daemon=True
    ).start()
