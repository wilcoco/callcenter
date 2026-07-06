"""FastAPI 앱: Twilio 음성 webhook + 티켓 조회 API."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from . import callbot, llm, services, twiml, ui
from .config import get_settings
from .database import get_db, init_db
from .models import Call, Team, Ticket

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("callcenter")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    agent = None
    if callbot.clawops_enabled():
        try:
            agent = callbot.build_agent()
            await agent.connect()
            log.info("ClawOps 음성봇 연결됨 (번호: %s)", get_settings().clawops_from_number)
        except Exception:
            log.exception("ClawOps 음성봇 연결 실패 — 웹/티켓 기능은 정상 동작합니다")
            agent = None
    else:
        log.info("ClawOps 미설정 — 음성봇 비활성 (CLAWOPS_API_KEY 등 필요)")
    yield
    if agent is not None:
        await agent.disconnect()


app = FastAPI(title="콜센터 자동 응대·팀 배정", version="0.1.0", lifespan=lifespan)
app.include_router(ui.router)


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------
def _action_url(request: Request, path: str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}{path}" if base else path


async def _verify_twilio(request: Request) -> None:
    """Twilio 서명 검증 (TWILIO_AUTH_TOKEN 설정 시에만)."""
    settings = get_settings()
    if not settings.verify_twilio_signature:
        return
    from twilio.request_validator import RequestValidator

    signature = request.headers.get("X-Twilio-Signature", "")
    form = await request.form()
    validator = RequestValidator(settings.twilio_auth_token)
    url = str(request.url)
    if not validator.validate(url, dict(form), signature):
        raise HTTPException(status_code=403, detail="invalid Twilio signature")


# ---------------------------------------------------------------------------
# Twilio 음성 webhook
# ---------------------------------------------------------------------------
@app.post("/voice/incoming")
async def voice_incoming(
    request: Request,
    db: Session = Depends(get_db),
    CallSid: str = Form(...),
    From: str = Form(""),
    To: str = Form(""),
):
    """전화 수신 시 최초 진입점 — 인사 후 음성 입력 받기."""
    await _verify_twilio(request)
    services.get_or_create_call(db, CallSid, from_number=From, to_number=To)
    xml = twiml.gather_response(twiml.GREETING, _action_url(request, "/voice/respond"))
    return Response(content=xml, media_type="application/xml")


@app.post("/voice/respond")
async def voice_respond(
    request: Request,
    db: Session = Depends(get_db),
    CallSid: str = Form(...),
    SpeechResult: str = Form(""),
    From: str = Form(""),
    To: str = Form(""),
):
    """고객 발화(SpeechResult) 처리 -> AI 응대 -> 다음 턴 or 종료."""
    await _verify_twilio(request)
    call = services.get_or_create_call(db, CallSid, from_number=From, to_number=To)
    settings = get_settings()

    speech = (SpeechResult or "").strip()
    if not speech:
        # 인식 실패 — 재안내 (이미 1턴 이상 진행됐다면 마무리)
        if call.turns >= 1:
            xml = twiml.say_and_hangup(twiml.GOODBYE)
            services.finalize_call(db, call)
        else:
            xml = twiml.gather_response(twiml.NO_INPUT, _action_url(request, "/voice/respond"))
        return Response(content=xml, media_type="application/xml")

    services.add_message(db, call, "caller", speech)

    history = [{"role": m.role, "text": m.text} for m in call.messages]
    result = llm.next_turn(history, turn_index=call.turns, max_turns=settings.max_turns)
    services.add_message(db, call, "agent", result["reply"])

    if result["should_end"]:
        services.finalize_call(db, call)
        xml = twiml.say_and_hangup(result["reply"] + " " + twiml.GOODBYE)
    else:
        xml = twiml.gather_response(result["reply"], _action_url(request, "/voice/respond"))
    return Response(content=xml, media_type="application/xml")


@app.post("/voice/status")
async def voice_status(
    request: Request,
    db: Session = Depends(get_db),
    CallSid: str = Form(...),
    CallStatus: str = Form(""),
):
    """통화 상태 콜백 — completed 시 분석/티켓 생성 보장(멱등)."""
    await _verify_twilio(request)
    call = db.query(Call).filter_by(call_sid=CallSid).one_or_none()
    if call is None:
        return JSONResponse({"ok": True, "note": "unknown call"})
    if CallStatus in {"completed", "busy", "failed", "no-answer", "canceled"}:
        services.finalize_call(db, call)
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# ClawOps webhook (선택) — 통화 상태 이벤트 안전장치
# ---------------------------------------------------------------------------
@app.post("/clawops/webhook")
async def clawops_webhook(request: Request):
    """ClawOps 콘솔에 등록하는 webhook 수신부.

    음성봇(WebSocket 에이전트)이 통화를 처리하므로 필수는 아니지만,
    서버 재시작 등으로 call_end 이벤트를 놓친 통화도 여기서
    분석·티켓 생성을 보장한다(멱등). CLAWOPS_SIGNING_KEY 설정 시 서명 검증.
    """
    form = dict(await request.form())
    settings = get_settings()

    if settings.clawops_signing_key:
        from clawops.webhooks import Webhooks, WebhookVerificationError

        base = settings.public_base_url.rstrip("/")
        url = f"{base}/clawops/webhook" if base else str(request.url)
        try:
            Webhooks().verify(
                url=url,
                params={k: str(v) for k, v in form.items()},
                signature=request.headers.get("X-Signature", ""),
                signing_key=settings.clawops_signing_key,
            )
        except WebhookVerificationError:
            raise HTTPException(status_code=403, detail="invalid ClawOps signature")

    call_id = form.get("CallId") or form.get("call_id") or ""
    status = (form.get("CallStatus") or form.get("status") or "").lower()
    log.info("ClawOps webhook: call=%s status=%s", call_id, status)

    if call_id and status in {"completed", "failed", "busy", "no-answer", "canceled"}:
        callbot.record_call_end(str(call_id))
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# 조회 API
# ---------------------------------------------------------------------------
def _ticket_dict(t: Ticket) -> dict:
    return {
        "id": t.id,
        "call_id": t.call_id,
        "team_key": t.team_key,
        "team_name": t.team_name,
        "title": t.title,
        "summary": t.summary,
        "priority": t.priority,
        "status": t.status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _call_dict(c: Call) -> dict:
    return {
        "id": c.id,
        "call_sid": c.call_sid,
        "from": c.from_number,
        "to": c.to_number,
        "status": c.status,
        "turns": c.turns,
        "intent": c.intent,
        "summary": c.summary,
        "transcript": c.transcript_text(),
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "ended_at": c.ended_at.isoformat() if c.ended_at else None,
        "ticket": _ticket_dict(c.ticket) if c.ticket else None,
    }


@app.get("/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "llm_enabled": s.llm_enabled,
        "clawops_enabled": callbot.clawops_enabled(),
    }


@app.get("/teams")
def list_teams(db: Session = Depends(get_db)):
    teams = db.query(Team).all()
    return [{"key": t.key, "name": t.name, "description": t.description, "email": t.email} for t in teams]


@app.get("/tickets")
def list_tickets(
    db: Session = Depends(get_db), team: str | None = None, status: str | None = None
):
    q = db.query(Ticket)
    if team:
        q = q.filter(Ticket.team_key == team)
    if status:
        q = q.filter(Ticket.status == status)
    return [_ticket_dict(t) for t in q.order_by(Ticket.id.desc()).all()]


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    t = db.get(Ticket, ticket_id)
    if not t:
        raise HTTPException(404, "ticket not found")
    return _ticket_dict(t)


@app.get("/calls")
def list_calls(db: Session = Depends(get_db)):
    calls = db.query(Call).order_by(Call.id.desc()).all()
    return [_call_dict(c) for c in calls]


@app.get("/calls/{call_id}")
def get_call(call_id: int, db: Session = Depends(get_db)):
    c = db.get(Call, call_id)
    if not c:
        raise HTTPException(404, "call not found")
    return _call_dict(c)
