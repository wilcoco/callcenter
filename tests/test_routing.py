from app import routing


def test_refund_keyword_routes_to_mgmt():
    assert routing.keyword_route("결제 환불 받고 싶어요") == "mgmt"


def test_it_keyword_routes_to_it():
    assert routing.keyword_route("로그인하면 자꾸 오류가 나고 접속이 안돼요") == "it"


def test_quote_keyword_routes_to_sales():
    assert routing.keyword_route("견적 받아서 주문하고 싶습니다") == "sales"


def test_quality_claim_routes_to_quality():
    assert routing.keyword_route("납품받은 제품에 불량이 있어 클레임 접수하려고요") == "quality"


def test_explicit_team_name_wins():
    # 구성원이 팀을 직접 지정하면 키워드보다 우선
    assert routing.keyword_route("생산기술팀에 전달해 주세요. 견적 관련 내용입니다") == "prodtech"
    assert routing.keyword_route("설계팀 앞으로 남길 내용이 있어요") == "design"


def test_explicit_executive_name_with_spaces():
    assert routing.keyword_route("회계담당 임원께 전달 부탁드립니다") == "exec_finance"
    assert routing.keyword_route("노무 담당 임원에게 남겨주세요") == "exec_labor"


def test_labor_dispute_routes_to_exec_labor():
    assert routing.keyword_route("임금체불 문제로 노동청에 진정을 넣었습니다") == "exec_labor"


def test_unknown_defaults_to_general():
    assert routing.keyword_route("그냥 안부 전화했어요") == "general"


def test_priority_urgent():
    assert routing.estimate_priority("지금 서비스 전체가 먹통이라 긴급합니다") == "urgent"


def test_priority_normal_default():
    assert routing.estimate_priority("문의가 있어서요") == "normal"


def test_agent_speaker_label_does_not_leak_into_routing():
    # "상담원:" 라벨의 '상담'이 영업팀 키워드로 오탐되면 안 됨 (회귀 테스트)
    from app import llm

    transcript = "고객: 그냥 일반적인 질문이 있어요\n상담원: 네, 말씀해 주세요"
    assert llm._fallback_analysis(transcript)["team_key"] == "general"


def test_normalize_invalid_team_key():
    assert routing.normalize_team_key("not-a-team") == "general"
    assert routing.normalize_team_key("quality") == "quality"
    assert routing.normalize_team_key("exec_labor") == "exec_labor"
    assert routing.normalize_team_key(None) == "general"
