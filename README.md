# 📞 콜센터 자동 응대 · 팀 자동 배정 시스템

회사 대표번호로 걸려온 **전화를 AI가 응대**하고, **대화 내용을 텍스트로 기록**한 뒤,
내용을 요약·분류해서 **담당 팀에 업무(티켓)를 자동 할당**하는 프로그램입니다.

> 질문하신 *"전화가 오면 대응하고, 대화 결과를 텍스트로 남기고, 그 결과를 관련 팀에 할당하는 프로그램이 가능한가?"* 에 대한
> 동작하는 구현체입니다. 답: **가능하며, 이 저장소가 그 예시입니다.**

---

## 동작 흐름

```
 전화 수신          AI 음성 응대            텍스트화·분석           팀 자동 배정
┌─────────┐      ┌──────────────┐      ┌───────────────┐      ┌──────────────┐
│ Twilio  │─────▶│  /voice/*    │─────▶│ Claude 요약·   │─────▶│ DB 티켓 생성 │
│ 인바운드│ HTTP │  음성봇 대화  │ 전문 │ 팀 분류·우선순위│ 결과 │ (담당팀 배정)│
└─────────┘      └──────────────┘      └───────────────┘      └──────────────┘
```

1. **전화 수신** — Twilio가 인바운드 전화를 `POST /voice/incoming` 으로 전달
2. **AI 응대** — `<Gather input="speech">` 로 고객 음성을 받아 STT → Claude가 한국어로 응대 (turn 반복)
3. **텍스트 기록** — 모든 발화를 `messages` 테이블에 저장 (통화 전문 보존)
4. **분석·배정** — 통화 종료 시 Claude가 전문을 읽고 `{담당팀, 제목, 요약, 우선순위}` 생성 → `tickets` 테이블에 자동 할당

> 💡 **API 키가 없어도 동작**합니다. `ANTHROPIC_API_KEY` 가 비어 있으면 키워드 기반 규칙 폴백으로 응대·분류해서
> 전체 파이프라인을 그대로 시연/테스트할 수 있습니다.

---

## 빠른 시작

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 필요 시 키 입력 (없어도 폴백으로 동작)

# 1) 실제 전화 없이 전체 흐름 시연
python -m scripts.simulate_call

# 2) 테스트
pytest -q

# 3) 서버 실행
uvicorn app.main:app --reload --port 8000
#  - 대시보드:  http://localhost:8000/
#  - 티켓 API:  http://localhost:8000/tickets
```

---

## Twilio 연동 (실제 전화 받기)

1. 서버를 공개 URL로 노출 (개발 중에는 `ngrok http 8000` 등)
2. `.env` 의 `PUBLIC_BASE_URL` 에 공개 URL 입력 (예: `https://abcd.ngrok.io`)
3. Twilio 콘솔 → 전화번호 → **Voice & Fax** 설정:
   - **A CALL COMES IN**: `Webhook` → `https://<공개URL>/voice/incoming` (HTTP POST)
   - **CALL STATUS CHANGES** (Status Callback): `https://<공개URL>/voice/status` (HTTP POST)
4. `.env` 의 `TWILIO_AUTH_TOKEN` 을 채우면 인바운드 요청 **서명 검증**이 자동 활성화됩니다.

이제 그 번호로 전화하면 AI가 응대하고, 끊으면 담당 팀 티켓이 생성됩니다.

---

## 구성

| 파일 | 역할 |
|------|------|
| `app/main.py` | FastAPI 앱 — Twilio webhook + 티켓/통화 조회 API + 대시보드 |
| `app/twiml.py` | Twilio 음성 응답(TwiML) 생성 (인사·음성수집·종료) |
| `app/llm.py` | Claude 연동 — 실시간 응대(`next_turn`) / 통화 분석(`analyze_call`) + 규칙 폴백 |
| `app/routing.py` | 키워드 기반 팀 분류·우선순위 추정 (폴백/검증) |
| `app/services.py` | 통화·메시지·티켓 도메인 로직 (분석→티켓 생성, 멱등) |
| `app/models.py` | DB 모델: `Team` / `Call` / `Message` / `Ticket` + 기본 팀 시드 |
| `app/database.py` | SQLAlchemy 엔진/세션, 초기화 |
| `app/config.py` | 환경설정(.env) |
| `scripts/simulate_call.py` | 전화 없이 전체 파이프라인 시연 |
| `tests/` | 라우팅 + 엔드투엔드 파이프라인 테스트 |

### 기본 팀 (분류 대상)

| key | 팀 | 담당 |
|-----|-----|------|
| `support` | 고객지원팀 | 사용법·일반 문의 |
| `billing` | 결제/청구팀 | 결제·환불·요금 |
| `tech` | 기술지원팀 | 오류·장애·버그 |
| `sales` | 영업팀 | 구매·견적·도입 |
| `general` | 일반/대표창구 | 분류 모호 시 기본값 |

팀 구성은 `app/models.py` 의 `DEFAULT_TEAMS` 에서 자유롭게 추가/수정할 수 있습니다.

---

## REST API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/voice/incoming` | (Twilio) 전화 수신 진입점 |
| `POST` | `/voice/respond` | (Twilio) 고객 음성 처리·AI 응대 |
| `POST` | `/voice/status` | (Twilio) 통화 상태 콜백·티켓 확정 |
| `GET` | `/tickets?team=&status=` | 티켓 목록 |
| `GET` | `/tickets/{id}` | 티켓 상세 |
| `GET` | `/calls`, `/calls/{id}` | 통화·전문(transcript) 조회 |
| `GET` | `/teams` | 팀 목록 |
| `GET` | `/health` | 상태 + LLM 활성 여부 |
| `GET` | `/` | 티켓 대시보드(HTML) |

---

## 확장 아이디어

- **할당 채널 추가**: 현재는 DB 티켓. 이 환경의 Gmail 연동으로 담당 팀 메일 발송, Slack/Jira 연동 등으로 확장 가능 (`services.finalize_call` 한 곳만 수정)
- **실시간 스트리밍**: 더 자연스러운 대화를 원하면 Twilio Media Streams + 실시간 STT로 교체
- **상담 이력 분석**: `calls`/`tickets` 데이터로 문의 유형 통계·대시보드
- **인증/대시보드 강화**: 담당자 로그인, 티켓 상태 변경(open→done) API

---

## 비용/주의

- Twilio: 전화번호 임대 + 통화/STT 사용량 과금
- Claude API: 응대·분석 토큰 사용량 과금 (응대는 저지연 모델, 분석은 고품질 모델 권장 — `.env` 에서 모델 분리 설정)
- 통화 녹취/개인정보는 관련 법규(개인정보보호법 등)에 맞춰 고지·보관 정책을 적용하세요.
