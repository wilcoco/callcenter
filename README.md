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

## 회사 지식 문서로 응대 내용 지정하기 (`knowledge/` 폴더)

AI가 대답할 내용을 **문서로 미리 제공**할 수 있습니다. `knowledge/` 폴더에
회사 정보·FAQ·정책(영업시간, 환불 규정, 요금제 등)을 담은 **.md 또는 .txt 파일**을
넣으면, AI 상담원이 통화 중 그 문서들을 근거로 답변합니다.

**문서 업로드 방법 (셋 중 아무거나):**

1. **GitHub 웹에서** — 저장소의 `knowledge/` 폴더 → `Add file` → `Upload files` 로 파일을 올리고
   커밋 → 서버에서 `git pull`
2. **서버에서 직접** — 서버의 `knowledge/` 폴더에 파일 복사 (`scp`, SFTP 등).
   재시작 없이 다음 통화부터 반영됩니다.
3. **로컬에서 git으로** — `knowledge/`에 파일 추가 후 `git add · commit · push` → 서버에서 `git pull`

**규칙:**

- 지원 형식은 `.md`, `.txt` (일반 텍스트). PDF·Word는 텍스트로 변환해서 넣으세요.
- 폴더 안 모든 파일을 파일명 순으로 읽어 합칩니다. 파일 추가/수정 시 **재시작 불필요**.
- 문서에 없는 내용은 추측하지 않고 "담당 팀 확인 후 연락드리겠다"고 안내하도록 지시되어 있습니다.
- 경로는 `.env` 의 `KNOWLEDGE_DIR` 로 변경 가능합니다 (단일 파일은 `KNOWLEDGE_FILE`).
- 문서 합계가 아주 큰 경우(수백 페이지 이상)는 프롬프트 주입 대신 RAG(검색 증강) 방식 도입을 권장합니다
  (현재는 합계 약 5만 자까지 사용하고 초과분은 잘립니다).

---

## Railway + PostgreSQL 배포

이 저장소에는 `Dockerfile` 이 포함되어 있어 Railway가 자동으로 빌드합니다.

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → 이 저장소 선택
2. 같은 프로젝트에 **PostgreSQL 추가** (`+ New` → Database → PostgreSQL)
3. 앱 서비스의 **Variables** 에 추가:

   | 변수 | 값 |
   |------|-----|
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (Railway 참조 문법) |
   | `ANTHROPIC_API_KEY` | Claude API 키 |
   | `TWILIO_AUTH_TOKEN` | Twilio Auth Token |
   | `PUBLIC_BASE_URL` | 배포된 도메인 (예: `https://xxx.up.railway.app`) |

4. **Settings → Networking → Generate Domain** 으로 공개 도메인 생성 → 그 값을 `PUBLIC_BASE_URL` 에 입력
5. Twilio 콘솔에서 webhook을 `https://xxx.up.railway.app/voice/incoming` / `/voice/status` 로 지정

⚠️ Railway의 디스크는 재배포 시 초기화되므로:
- **DB는 반드시 PostgreSQL 사용** (SQLite 파일은 사라짐) — 위 2·3번이 그 설정입니다.
- **knowledge/ 문서는 git에 커밋해서 배포**하세요 (서버에서 직접 수정하면 재배포 때 사라짐).

## 웹 화면 (메뉴)

배포된 주소로 접속하면 담당자가 쓰는 관리 화면이 열립니다:

| 메뉴 | 경로 | 내용 |
|------|------|------|
| **대시보드** | `/` | 총 통화/티켓/미처리/긴급 통계, 팀별 미처리 업무, 최근 티켓 |
| **티켓** | `/ui/tickets` | 팀·상태별 필터, 접수→처리중→완료 상태 변경 버튼 |
| **통화 기록** | `/ui/calls` | 통화 목록, 클릭하면 대화 전문(채팅 형태)·요약·배정 티켓 상세 |

---

## 전화 연동 ① — ClawOps 국내 070 번호 (권장)

[ClawOps](https://claw-ops.com)로 **국내 070 번호**를 받아 실시간 AI 음성 통화로 응대합니다.
고객은 국내 통화 요금만 부담하며, 기존 1588 등 대표번호 착신 연계도 가능합니다.

**준비물 (환경변수 5개):**

| 변수 | 발급처 |
|------|--------|
| `CLAWOPS_API_KEY`, `CLAWOPS_ACCOUNT_ID`, `CLAWOPS_FROM_NUMBER`(070번호) | [claw-ops.com](https://claw-ops.com) 가입 (3일 무료 체험) |
| `DEEPGRAM_API_KEY` (음성 인식) | [deepgram.com](https://deepgram.com) — 무료 크레딧 제공 |
| `ELEVENLABS_API_KEY` (음성 합성) | [elevenlabs.io](https://elevenlabs.io) — 무료 플랜 제공 |

`ANTHROPIC_API_KEY` 포함 위 변수들을 채우면 서버 시작 시 음성봇이 자동으로 연결됩니다
(`/health` 에서 `clawops_enabled: true` 확인). 미설정 시 웹/티켓 기능만 동작합니다.

동작: 070 번호로 전화 → Deepgram이 한국어 음성 인식 → Claude가 실시간 응대(끼어들기 지원)
→ ElevenLabs가 음성 합성 → 통화 종료 시 자동으로 요약·팀 배정·티켓 생성.
AI가 용건 파악을 마치면 스스로 정중히 통화를 종료합니다.

## 전화 연동 ② — Twilio (해외 번호, 선택)

해외 번호가 필요한 경우 Twilio webhook 방식도 지원합니다.

1. 서버를 공개 URL로 노출 (개발 중에는 `ngrok http 8000` 등)
2. `.env` 의 `PUBLIC_BASE_URL` 에 공개 URL 입력
3. Twilio 콘솔 → 전화번호 → Voice 설정:
   - **A CALL COMES IN**: `https://<공개URL>/voice/incoming` (HTTP POST)
   - **CALL STATUS CHANGES**: `https://<공개URL>/voice/status` (HTTP POST)
4. `TWILIO_AUTH_TOKEN` 설정 시 인바운드 서명 검증 자동 활성화

참고: Twilio는 한국(+82) 음성 번호를 제공하지 않아, 한국 고객 대상 서비스에는 ①을 사용하세요.

---

## 구성

| 파일 | 역할 |
|------|------|
| `app/main.py` | FastAPI 앱 — webhook + 티켓/통화 조회 API + 음성봇 기동 |
| `app/callbot.py` | ClawOps 실시간 음성봇 (국내 070 번호, STT/LLM/TTS 파이프라인) |
| `app/twiml.py` | Twilio 음성 응답(TwiML) 생성 (해외 번호용) |
| `app/llm.py` | Claude 연동 — 실시간 응대(`next_turn`) / 통화 분석(`analyze_call`) + 규칙 폴백 |
| `app/routing.py` | 키워드 기반 팀 분류·우선순위 추정 (폴백/검증) |
| `app/services.py` | 통화·메시지·티켓 도메인 로직 (분석→티켓 생성, 멱등) |
| `app/models.py` | DB 모델: `Team` / `Call` / `Message` / `Ticket` + 기본 팀 시드 |
| `app/database.py` | SQLAlchemy 엔진/세션, 초기화 |
| `app/config.py` | 환경설정(.env) |
| `scripts/simulate_call.py` | 전화 없이 전체 파이프라인 시연 |
| `tests/` | 라우팅 + 엔드투엔드 파이프라인 테스트 |

### 기본 팀 (분류 대상)

**실무 팀 (12)**

| key | 팀 | 담당 |
|-----|-----|------|
| `production` | 생산팀 | 생산·제조 현장, 생산 일정 |
| `prodtech` | 생산기술팀 | 설비·공정 기술, 금형·치공구 |
| `quality` | 양산품질팀 | 품질·불량·검사·클레임 |
| `partner` | 상생협력팀 | 협력사·외주, 업체 등록 |
| `material` | 자재관리팀 | 자재·재고·입출고·납기 |
| `sales` | 영업관리팀 | 수주·견적·주문·납품·계약 |
| `mgmt` | 경영관리팀 | 총무·인사·회계 실무, 세금계산서·급여·대금 |
| `it` | 전산팀 | 전산·ERP·PC·네트워크 |
| `hampyeong` | 함평팀 | 함평 사업장 업무 |
| `escon` | 에스콘 | 에스콘 관련 업무 |
| `design` | 설계팀 | 설계·도면·사양 |
| `rnd` | 개발팀 | 신제품 개발·연구·시제품 |

**임원 (7)** — 경영 판단이 필요한 중대 사안에만 배정되도록 AI에 원칙이 주어져 있습니다.

| key | 직책 |
|-----|------|
| `exec_finance` | 회계담당임원 |
| `exec_labor` | 노무담당임원 |
| `ceo_mgmt` | 관리각자대표 |
| `ceo_prod` | 생산각자대표 |
| `exec_prod` | 생산담당임원 |
| `exec_quality` | 품질담당임원 |
| `exec_rnd` | 연구개발담당임원 |

분류가 모호하면 `general`(일반/대표창구)로 배정됩니다.
팀 구성은 `app/models.py` 의 `DEFAULT_TEAMS` 에서 자유롭게 추가/수정할 수 있으며,
서버 시작 시 DB의 팀 목록이 이 정의에 맞게 자동 동기화됩니다.

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
