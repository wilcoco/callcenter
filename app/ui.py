"""서버 렌더링 웹 UI — 대시보드 / 티켓 / 통화 메뉴."""
from __future__ import annotations

import html
import os

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import get_db
from .models import Call, GlossaryTerm, KnowledgeDoc, Team, Ticket

router = APIRouter()

_PRIORITY_LABEL = {"low": "낮음", "normal": "보통", "high": "높음", "urgent": "긴급"}
_STATUS_LABEL = {"open": "접수", "in_progress": "처리중", "done": "완료"}

_STYLE = """
*{box-sizing:border-box}body{font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
margin:0;background:#f5f6f8;color:#222}
nav{background:#1f2937;padding:0 1.5rem;display:flex;gap:.25rem;align-items:center}
nav .brand{color:#fff;font-weight:700;padding:.7rem .9rem .7rem 0;font-size:1.05rem;
display:flex;align-items:center;gap:.6rem}
nav .brand img{height:40px;display:block;background:#fff;border-radius:9px;padding:3px 6px}
nav .brand .name{color:#fff;font-weight:700;font-size:1.02rem}
nav .brand .mark{font-size:1.25rem;font-weight:800;letter-spacing:.06em;
background:linear-gradient(135deg,#60a5fa,#3b82f6);-webkit-background-clip:text;
background-clip:text;color:transparent}
nav .brand .sub{color:#9ca3af;font-size:.8rem;font-weight:500}
nav a{color:#cbd5e1;text-decoration:none;padding:1rem .9rem;display:inline-block}
nav a:hover{color:#fff}nav a.active{color:#fff;box-shadow:inset 0 -3px 0 #3b82f6}
main{max-width:1000px;margin:1.5rem auto;padding:0 1rem}
h1{font-size:1.3rem;margin:.2rem 0 1rem}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:8px;overflow:hidden;
box-shadow:0 1px 3px rgba(0,0,0,.08)}
td,th{border-bottom:1px solid #eee;padding:.6rem .7rem;text-align:left;font-size:.92rem}
th{background:#f9fafb;color:#555;font-weight:600}
tr:last-child td{border-bottom:none}
a.row-link{color:#2563eb;text-decoration:none}a.row-link:hover{text-decoration:underline}
.cards{display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1.4rem}
.card{background:#fff;border-radius:8px;padding:1rem 1.3rem;min-width:140px;flex:1;
box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card .num{font-size:1.7rem;font-weight:700}.card .lbl{color:#666;font-size:.85rem}
.badge{display:inline-block;padding:.15rem .55rem;border-radius:99px;font-size:.78rem;font-weight:600}
.p-low{background:#e5e7eb;color:#374151}.p-normal{background:#dbeafe;color:#1d4ed8}
.p-high{background:#ffedd5;color:#c2410c}.p-urgent{background:#fee2e2;color:#b91c1c}
.s-open{background:#fef9c3;color:#854d0e}.s-in_progress{background:#dbeafe;color:#1d4ed8}
.s-done{background:#dcfce7;color:#166534}
.filters{margin-bottom:.8rem;display:flex;gap:.5rem;flex-wrap:wrap}
.filters a{background:#fff;border:1px solid #ddd;border-radius:6px;padding:.3rem .7rem;
text-decoration:none;color:#333;font-size:.85rem}
.filters a.on{background:#1f2937;color:#fff;border-color:#1f2937}
.chat{background:#fff;border-radius:8px;padding:1rem;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.msg{margin:.5rem 0;display:flex}.msg .bubble{max-width:75%;padding:.5rem .8rem;border-radius:12px;
font-size:.92rem;white-space:pre-wrap}
.msg.caller .bubble{background:#e0e7ff}.msg.agent{justify-content:flex-end}
.msg.agent .bubble{background:#f1f5f9}
.msg .who{font-size:.72rem;color:#888;margin:0 .4rem;align-self:flex-end}
.detail{background:#fff;border-radius:8px;padding:1rem 1.3rem;margin-bottom:1rem;
box-shadow:0 1px 3px rgba(0,0,0,.08)}
.detail dt{color:#666;font-size:.8rem;margin-top:.6rem}.detail dd{margin:.15rem 0 0}
form.inline{display:inline}
button.act{border:1px solid #ccc;background:#fff;border-radius:6px;padding:.25rem .6rem;
cursor:pointer;font-size:.8rem;margin-right:.25rem}
button.act:hover{background:#f3f4f6}
select.team-select{border:1px solid #ccc;border-radius:6px;padding:.2rem .3rem;
font-size:.8rem;max-width:130px;margin-right:.25rem}
.sub-text{color:#666;font-size:.83rem}
.glossary-add{background:#fff;border-radius:8px;padding:1rem 1.2rem;margin-bottom:1.2rem;
box-shadow:0 1px 3px rgba(0,0,0,.08)}
.g-row{display:flex;gap:1rem;flex-wrap:wrap}.g-row>div{flex:1;min-width:200px}
.empty{color:#888;padding:2rem;text-align:center}
input[type=text],textarea{width:100%;border:1px solid #ccc;border-radius:6px;padding:.55rem .7rem;
font-size:.95rem;font-family:inherit;background:#fff}
textarea{min-height:320px;line-height:1.5}
label{display:block;margin:.9rem 0 .3rem;color:#555;font-size:.85rem}
button.primary{background:#1f2937;color:#fff;border:none;border-radius:6px;
padding:.55rem 1.2rem;font-size:.95rem;cursor:pointer;margin-top:1rem}
button.primary:hover{background:#374151}
a.btn{display:inline-block;background:#1f2937;color:#fff;border-radius:6px;
padding:.45rem .9rem;text-decoration:none;font-size:.88rem;margin-bottom:.8rem}
button.danger{border:1px solid #fca5a5;background:#fff;color:#b91c1c;border-radius:6px;
padding:.25rem .6rem;cursor:pointer;font-size:.8rem}
button.danger:hover{background:#fef2f2}
.hint{color:#777;font-size:.83rem;margin:.4rem 0 1rem}
"""


def _e(text) -> str:
    return html.escape(str(text or ""))


_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _brand_html() -> str:
    """app/static/logo.(png|jpg|svg) 파일이 있으면 이미지 로고, 없으면 워드마크.

    png/jpg를 먼저 찾으므로, 실제 로고 원본 파일을 올리면 SVG 재현본을 대체한다.
    """
    for name in ("logo.png", "logo.jpg", "logo.svg"):
        if os.path.isfile(os.path.join(_STATIC_DIR, name)):
            return (
                f'<img src="/static/{name}" alt="주식회사 캠스">'
                '<span class="name">주식회사 캠스</span> <span class="sub">콜센터</span>'
            )
    return '<span class="mark">CAMS</span> <span class="sub">주식회사 캠스 콜센터</span>'


def _page(title: str, body: str, active: str) -> str:
    def nav_cls(key: str) -> str:
        return ' class="active"' if key == active else ""

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)} — 캠스 콜센터</title><style>{_STYLE}</style></head><body>
<nav><span class="brand">{_brand_html()}</span>
<a href="/"{nav_cls('dash')}>대시보드</a>
<a href="/ui/tickets"{nav_cls('tickets')}>티켓</a>
<a href="/ui/calls"{nav_cls('calls')}>통화 기록</a>
<a href="/ui/knowledge"{nav_cls('knowledge')}>지식 문서</a>
<a href="/ui/glossary"{nav_cls('glossary')}>용어 사전</a>
</nav><main><h1>{_e(title)}</h1>{body}</main></body></html>"""


def _priority_badge(p: str) -> str:
    return f'<span class="badge p-{_e(p)}">{_e(_PRIORITY_LABEL.get(p, p))}</span>'


def _status_badge(s: str) -> str:
    return f'<span class="badge s-{_e(s)}">{_e(_STATUS_LABEL.get(s, s))}</span>'


def _fmt_dt(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "-"


# ---------------------------------------------------------------------------
# 대시보드
# ---------------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
def dashboard(db: Session = Depends(get_db)):
    total_calls = db.query(func.count(Call.id)).scalar() or 0
    total_tickets = db.query(func.count(Ticket.id)).scalar() or 0
    open_tickets = (
        db.query(func.count(Ticket.id)).filter(Ticket.status != "done").scalar() or 0
    )
    urgent = (
        db.query(func.count(Ticket.id))
        .filter(Ticket.priority == "urgent", Ticket.status != "done")
        .scalar()
        or 0
    )

    team_counts = dict(
        db.query(Ticket.team_name, func.count(Ticket.id))
        .filter(Ticket.status != "done")
        .group_by(Ticket.team_name)
        .all()
    )
    team_rows = "".join(
        f"<tr><td>{_e(name)}</td><td>{count}</td></tr>" for name, count in team_counts.items()
    ) or '<tr><td colspan="2" class="empty">미처리 티켓 없음</td></tr>'

    recent = db.query(Ticket).order_by(Ticket.id.desc()).limit(10).all()
    recent_rows = "".join(
        f"<tr><td>#{t.id}</td><td>{_e(t.team_name)}</td>"
        f"<td>{_priority_badge(t.priority)}</td>"
        f'<td><a class="row-link" href="/ui/calls/{t.call_id}">{_e(t.title)}</a></td>'
        f"<td>{_status_badge(t.status)}</td><td>{_fmt_dt(t.created_at)}</td></tr>"
        for t in recent
    ) or '<tr><td colspan="6" class="empty">아직 티켓이 없습니다.</td></tr>'

    body = f"""
<div class="cards">
<div class="card"><div class="num">{total_calls}</div><div class="lbl">총 통화</div></div>
<div class="card"><div class="num">{total_tickets}</div><div class="lbl">총 티켓</div></div>
<div class="card"><div class="num">{open_tickets}</div><div class="lbl">미처리 티켓</div></div>
<div class="card"><div class="num">{urgent}</div><div class="lbl">긴급</div></div>
</div>
<h1>팀별 미처리 업무</h1>
<table><tr><th>팀</th><th>건수</th></tr>{team_rows}</table>
<h1 style="margin-top:1.5rem">최근 티켓</h1>
<table><tr><th>번호</th><th>담당팀</th><th>우선순위</th><th>제목</th><th>상태</th><th>접수</th></tr>
{recent_rows}</table>"""
    return _page("대시보드", body, "dash")


# ---------------------------------------------------------------------------
# 티켓 목록 / 상태 변경
# ---------------------------------------------------------------------------
@router.get("/ui/tickets", response_class=HTMLResponse)
def tickets_page(
    db: Session = Depends(get_db), team: str = "", status: str = ""
):
    q = db.query(Ticket).order_by(Ticket.id.desc())
    if team:
        q = q.filter(Ticket.team_key == team)
    if status:
        q = q.filter(Ticket.status == status)
    tickets = q.limit(200).all()

    teams = db.query(Team).all()

    def flink(label: str, t: str, s: str, on: bool) -> str:
        qs = []
        if t:
            qs.append(f"team={t}")
        if s:
            qs.append(f"status={s}")
        href = "/ui/tickets" + ("?" + "&".join(qs) if qs else "")
        return f'<a href="{href}" class="{"on" if on else ""}">{_e(label)}</a>'

    team_filters = flink("전체 팀", "", status, not team) + "".join(
        flink(tm.name, tm.key, status, team == tm.key) for tm in teams
    )
    status_filters = flink("전체 상태", team, "", not status) + "".join(
        flink(label, team, key, status == key) for key, label in _STATUS_LABEL.items()
    )

    def actions(t: Ticket) -> str:
        buttons = []
        for key, label in _STATUS_LABEL.items():
            if key != t.status:
                buttons.append(
                    f'<form class="inline" method="post" action="/ui/tickets/{t.id}/status">'
                    f'<input type="hidden" name="status" value="{key}">'
                    f'<button class="act">{_e(label)}</button></form>'
                )
        return "".join(buttons)

    def team_selector(t: Ticket) -> str:
        options = "".join(
            f'<option value="{tm.key}"{" selected" if tm.key == t.team_key else ""}>{_e(tm.name)}</option>'
            for tm in teams
        )
        return (
            f'<form class="inline" method="post" action="/ui/tickets/{t.id}/team">'
            f'<select name="team_key" class="team-select">{options}</select>'
            f'<button class="act">변경</button></form>'
        )

    def contact_cell(t: Ticket) -> str:
        parts = []
        if t.caller_name:
            parts.append(_e(t.caller_name))
        if t.callback:
            parts.append(f'<span class="sub-text">{_e(t.callback)}</span>')
        return "<br>".join(parts) or "-"

    rows = "".join(
        f"<tr><td>#{t.id}</td><td>{_e(t.team_name)}<br>{team_selector(t)}</td>"
        f"<td>{contact_cell(t)}</td>"
        f"<td>{_priority_badge(t.priority)}</td>"
        f'<td><a class="row-link" href="/ui/calls/{t.call_id}">{_e(t.title)}</a></td>'
        f"<td>{_status_badge(t.status)}</td><td>{_fmt_dt(t.created_at)}</td>"
        f"<td>{actions(t)}</td></tr>"
        for t in tickets
    ) or '<tr><td colspan="8" class="empty">조건에 맞는 티켓이 없습니다.</td></tr>'

    body = f"""
<div class="filters">{team_filters}</div>
<div class="filters">{status_filters}</div>
<table><tr><th>번호</th><th>담당팀 (변경 가능)</th><th>문의자/연락처</th><th>우선순위</th><th>제목</th><th>상태</th><th>접수</th><th>상태 변경</th></tr>
{rows}</table>"""
    return _page("티켓", body, "tickets")


@router.post("/ui/tickets/{ticket_id}/team")
def change_ticket_team(
    ticket_id: int, team_key: str = Form(...), db: Session = Depends(get_db)
):
    """관리자가 자동 배정된 팀을 다른 팀으로 재배정."""
    team = db.query(Team).filter_by(key=team_key).one_or_none()
    if team is None:
        raise HTTPException(400, "invalid team")
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, "ticket not found")
    ticket.team_key = team.key
    ticket.team_name = team.name
    db.flush()
    return RedirectResponse("/ui/tickets", status_code=303)


@router.post("/ui/tickets/{ticket_id}/status")
def change_ticket_status(
    ticket_id: int, status: str = Form(...), db: Session = Depends(get_db)
):
    if status not in _STATUS_LABEL:
        raise HTTPException(400, "invalid status")
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, "ticket not found")
    ticket.status = status
    db.flush()
    return RedirectResponse("/ui/tickets", status_code=303)


# ---------------------------------------------------------------------------
# 지식 문서 (회사 규정/FAQ — AI 응대에 반영)
# ---------------------------------------------------------------------------
@router.get("/ui/knowledge", response_class=HTMLResponse)
def knowledge_page(db: Session = Depends(get_db)):
    docs = db.query(KnowledgeDoc).order_by(KnowledgeDoc.title).all()
    rows = "".join(
        f'<tr><td><a class="row-link" href="/ui/knowledge/{d.id}">{_e(d.title)}</a></td>'
        f"<td>{len(d.content or '')}자</td><td>{_fmt_dt(d.updated_at)}</td>"
        f'<td><form class="inline" method="post" action="/ui/knowledge/{d.id}/delete" '
        f"onsubmit=\"return confirm('『{_e(d.title)}』 문서를 삭제할까요?')\">"
        f'<button class="danger">삭제</button></form></td></tr>'
        for d in docs
    ) or '<tr><td colspan="4" class="empty">등록된 문서가 없습니다. 회사 규정·FAQ를 등록해 보세요.</td></tr>'

    body = f"""
<p class="hint">여기 등록한 문서는 AI 상담원이 통화 중 답변 근거로 사용합니다.
등록·수정 즉시 다음 통화부터 반영됩니다. 민감 정보(급여 등)는 올리지 마세요.</p>
<a class="btn" href="/ui/knowledge/new">+ 새 문서</a>
<table><tr><th>제목</th><th>분량</th><th>수정일</th><th></th></tr>{rows}</table>"""
    return _page("지식 문서", body, "knowledge")


def _knowledge_form(action: str, title: str = "", content: str = "") -> str:
    return f"""
<form method="post" action="{action}">
<label>문서 제목 (예: 휴가규정, 경비처리 절차)</label>
<input type="text" name="title" required maxlength="255" value="{_e(title)}">
<label>내용</label>
<textarea name="content" placeholder="규정/FAQ 내용을 붙여넣으세요. 일반 텍스트면 충분합니다.">{_e(content)}</textarea>
<button class="primary">저장</button>
</form>"""


@router.get("/ui/knowledge/new", response_class=HTMLResponse)
def knowledge_new_page():
    return _page("새 지식 문서", _knowledge_form("/ui/knowledge"), "knowledge")


@router.post("/ui/knowledge")
def knowledge_create(
    title: str = Form(...), content: str = Form(""), db: Session = Depends(get_db)
):
    db.add(KnowledgeDoc(title=title.strip() or "제목 없음", content=content))
    db.flush()
    return RedirectResponse("/ui/knowledge", status_code=303)


@router.get("/ui/knowledge/{doc_id}", response_class=HTMLResponse)
def knowledge_edit_page(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDoc, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    return _page(
        f"문서 수정 — {doc.title}",
        _knowledge_form(f"/ui/knowledge/{doc.id}", doc.title, doc.content or ""),
        "knowledge",
    )


@router.post("/ui/knowledge/{doc_id}")
def knowledge_update(
    doc_id: int,
    title: str = Form(...),
    content: str = Form(""),
    db: Session = Depends(get_db),
):
    doc = db.get(KnowledgeDoc, doc_id)
    if not doc:
        raise HTTPException(404, "document not found")
    doc.title = title.strip() or doc.title
    doc.content = content
    db.flush()
    return RedirectResponse("/ui/knowledge", status_code=303)


@router.post("/ui/knowledge/{doc_id}/delete")
def knowledge_delete(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(KnowledgeDoc, doc_id)
    if doc:
        db.delete(doc)
        db.flush()
    return RedirectResponse("/ui/knowledge", status_code=303)


# ---------------------------------------------------------------------------
# 용어 사전 (음성 인식 교정용 주요 단어)
# ---------------------------------------------------------------------------
@router.get("/ui/glossary", response_class=HTMLResponse)
def glossary_page(db: Session = Depends(get_db)):
    terms = db.query(GlossaryTerm).order_by(GlossaryTerm.term).all()
    rows = "".join(
        f"<tr><td><strong>{_e(t.term)}</strong></td>"
        f'<td>{_e(t.aliases) or "-"}</td><td>{_e(t.note) or "-"}</td>'
        f'<td><form class="inline" method="post" action="/ui/glossary/{t.id}/delete" '
        f"onsubmit=\"return confirm('『{_e(t.term)}』 삭제할까요?')\">"
        f'<button class="danger">삭제</button></form></td></tr>'
        for t in terms
    ) or '<tr><td colspan="4" class="empty">등록된 단어가 없습니다. 설비명·제품명·약칭 등을 등록하세요.</td></tr>'

    body = f"""
<p class="hint">전화 음성에서 자주 나오는 회사 고유 단어(설비명, 제품명, 부서 약칭, 거래처 등)를
등록하면 AI가 비슷한 발음을 이 단어로 알아듣습니다. 등록 즉시 다음 통화부터 반영됩니다.</p>
<form method="post" action="/ui/glossary" class="glossary-add">
<div class="g-row">
<div><label>단어 *</label><input type="text" name="term" required placeholder="예: 생산기술팀 / 1호기 / 사출기"></div>
<div><label>비슷하게 들리는 발음 (선택, 쉼표로 구분)</label><input type="text" name="aliases" placeholder="예: 정수기술팀, 생기팀"></div>
<div><label>메모 (선택)</label><input type="text" name="note" placeholder="예: 조립 2라인 설비"></div>
</div>
<button class="primary">단어 추가</button>
</form>
<table><tr><th>단어</th><th>비슷한 발음</th><th>메모</th><th></th></tr>{rows}</table>"""
    return _page("용어 사전", body, "glossary")


@router.post("/ui/glossary")
def glossary_create(
    term: str = Form(...),
    aliases: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
):
    term = term.strip()
    if term:
        db.add(GlossaryTerm(term=term, aliases=aliases.strip(), note=note.strip()))
        db.flush()
    return RedirectResponse("/ui/glossary", status_code=303)


@router.post("/ui/glossary/{term_id}/delete")
def glossary_delete(term_id: int, db: Session = Depends(get_db)):
    t = db.get(GlossaryTerm, term_id)
    if t:
        db.delete(t)
        db.flush()
    return RedirectResponse("/ui/glossary", status_code=303)


# ---------------------------------------------------------------------------
# 통화 목록 / 상세(전문)
# ---------------------------------------------------------------------------
@router.get("/ui/calls", response_class=HTMLResponse)
def calls_page(db: Session = Depends(get_db)):
    calls = db.query(Call).order_by(Call.id.desc()).limit(200).all()
    rows = "".join(
        f'<tr><td><a class="row-link" href="/ui/calls/{c.id}">#{c.id}</a></td>'
        f"<td>{_e(c.from_number)}</td><td>{_e(c.status)}</td><td>{c.turns}</td>"
        f"<td>{_e(c.intent or '-')}</td>"
        f"<td>{_e((c.ticket.team_name if c.ticket else '-'))}</td>"
        f"<td>{_fmt_dt(c.started_at)}</td></tr>"
        for c in calls
    ) or '<tr><td colspan="7" class="empty">아직 통화 기록이 없습니다.</td></tr>'

    body = f"""<table>
<tr><th>번호</th><th>발신번호</th><th>상태</th><th>대화턴</th><th>용건</th><th>배정팀</th><th>시작</th></tr>
{rows}</table>"""
    return _page("통화 기록", body, "calls")


@router.get("/ui/calls/{call_id}", response_class=HTMLResponse)
def call_detail_page(call_id: int, db: Session = Depends(get_db)):
    call = db.get(Call, call_id)
    if not call:
        raise HTTPException(404, "call not found")

    bubbles = "".join(
        f'<div class="msg {m.role}">'
        + (
            f'<div class="bubble">{_e(m.text)}</div><span class="who">상담원</span>'
            if m.role == "agent"
            else f'<span class="who">고객</span><div class="bubble">{_e(m.text)}</div>'
        )
        + "</div>"
        for m in call.messages
    ) or '<div class="empty">대화 내용이 없습니다.</div>'

    ticket_html = ""
    if call.ticket:
        t = call.ticket
        ticket_html = f"""
<div class="detail"><strong>🎫 배정된 티켓 #{t.id}</strong>
<dl>
<dt>담당팀</dt><dd>{_e(t.team_name)} {_priority_badge(t.priority)} {_status_badge(t.status)}</dd>
<dt>문의자</dt><dd>{_e(t.caller_name or '-')}</dd>
<dt>회신 연락처</dt><dd>{_e(t.callback or '-')}</dd>
<dt>제목</dt><dd>{_e(t.title)}</dd>
<dt>요약</dt><dd>{_e(t.summary)}</dd>
</dl></div>"""

    body = f"""
<div class="detail">
<dl>
<dt>발신번호</dt><dd>{_e(call.from_number or '-')}</dd>
<dt>통화 시간</dt><dd>{_fmt_dt(call.started_at)} ~ {_fmt_dt(call.ended_at)}</dd>
<dt>용건</dt><dd>{_e(call.intent or '-')}</dd>
<dt>요약</dt><dd>{_e(call.summary or '-')}</dd>
</dl></div>
{ticket_html}
<h1>대화 전문</h1>
<div class="chat">{bubbles}</div>"""
    return _page(f"통화 #{call.id}", body, "calls")
