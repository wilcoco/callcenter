"""실제 전화 없이 전체 파이프라인을 시연하는 스크립트.

Twilio webhook을 흉내내어 한 통화를 처음부터 끝까지 진행하고,
생성된 티켓을 출력합니다.

    python -m scripts.simulate_call
"""
from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app

# 가짜 고객 발화 시나리오 (원하는 대로 바꿔보세요)
SCENARIO = [
    "결제가 두 번 됐는데 환불받고 싶어요.",
    "지난주 토요일에 카드로 결제했어요. 금액은 삼만원이요.",
    "네, 그게 다예요. 빨리 처리 부탁드려요.",
]


def main() -> int:
    init_db()
    client = TestClient(app)
    sid = "CA_SIMULATED_0001"

    print("=== 전화 수신 ===")
    r = client.post("/voice/incoming", data={"CallSid": sid, "From": "+821012345678", "To": "+8225550000"})
    print(r.text, "\n")

    for utterance in SCENARIO:
        print(f"고객> {utterance}")
        r = client.post("/voice/respond", data={"CallSid": sid, "SpeechResult": utterance})
        print("TwiML>", r.text, "\n")
        if "Hangup" in r.text:
            break

    # 통화 종료 콜백
    client.post("/voice/status", data={"CallSid": sid, "CallStatus": "completed"})

    print("=== 생성된 티켓 ===")
    tickets = client.get("/tickets").json()
    for t in tickets:
        print(f"#{t['id']} [{t['team_name']} / {t['priority']}] {t['title']}")
        print(f"   요약: {t['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
