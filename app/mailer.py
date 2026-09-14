"""SMTP 이메일 발송 (담당 팀 접수 알림).

SMTP 설정(config)이 없으면 조용히 건너뛴다. 발송 실패는 예외를 던지지 않고
로그만 남긴다 — 이메일은 부가 알림이라 통화/티켓 처리를 막지 않는다.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from .config import get_settings

log = logging.getLogger("callcenter.mailer")

_PLACEHOLDER_DOMAINS = ("example.com", "example.org")


def resolve_recipient(team_email: str | None) -> str:
    """팀 이메일이 실제 주소면 그걸, 아니면 기본 수신처(notify_email)를 반환."""
    email = (team_email or "").strip()
    if email and "@" in email and not email.endswith(_PLACEHOLDER_DOMAINS):
        return email
    return get_settings().notify_email.strip()


def _normalize_recipients(to) -> list[str]:
    if isinstance(to, str):
        items = to.split(",")
    else:
        items = list(to or [])
    seen: list[str] = []
    for x in items:
        e = (x or "").strip()
        if e and "@" in e and e.lower() not in [s.lower() for s in seen]:
            seen.append(e)
    return seen


def send_email(to, subject: str, body: str) -> bool:
    """일반 텍스트 메일 발송. to는 문자열/쉼표목록/리스트 가능. 성공 True."""
    s = get_settings()
    if not s.email_enabled:
        log.info("SMTP 미설정 — 이메일 발송 건너뜀")
        return False
    recipients = _normalize_recipients(to)
    if not recipients:
        log.info("수신처 없음 — 이메일 발송 건너뜀")
        return False

    msg = EmailMessage()
    from_addr = (s.smtp_from or s.smtp_user).strip()
    msg["From"] = formataddr(("주식회사 캠스 콜센터", from_addr))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if s.smtp_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=context) as server:
                server.login(s.smtp_user, s.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(s.smtp_user, s.smtp_password)
                server.send_message(msg)
        log.info("이메일 발송 완료: %s (%s)", ", ".join(recipients), subject)
        return True
    except Exception as exc:  # pragma: no cover - 외부 SMTP 방어
        log.warning("이메일 발송 실패(%s): %s", ", ".join(recipients), exc)
        return False


_PRIORITY_LABEL = {"low": "낮음", "normal": "보통", "high": "높음", "urgent": "긴급"}


def build_ticket_email(ticket_info: dict) -> tuple[str, str]:
    """티켓 정보 dict → (제목, 본문). ticket_info 키:
    team_name, title, priority, caller_name, callback, summary, transcript,
    call_id, created_at, dashboard_url
    """
    pr = _PRIORITY_LABEL.get(ticket_info.get("priority", "normal"), ticket_info.get("priority", ""))
    subject = f"[캠스 접수] {ticket_info.get('team_name','')} - {ticket_info.get('title','전화 문의')}"
    lines = [
        f"■ 담당팀: {ticket_info.get('team_name','')}",
        f"■ 우선순위: {pr}",
        f"■ 문의자: {ticket_info.get('caller_name') or '-'}",
        f"■ 회신 연락처: {ticket_info.get('callback') or '-'}",
        f"■ 접수시각: {ticket_info.get('created_at') or '-'}",
        "",
        f"■ 용건: {ticket_info.get('title','')}",
        "",
        "■ 요약",
        ticket_info.get("summary") or "-",
        "",
        "■ 통화 전문",
        ticket_info.get("transcript") or "-",
    ]
    if ticket_info.get("dashboard_url"):
        lines += ["", f"대시보드에서 보기: {ticket_info['dashboard_url']}"]
    return subject, "\n".join(lines)
