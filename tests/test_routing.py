from app import routing


def test_billing_keyword_routes_to_billing():
    assert routing.keyword_route("결제 환불 받고 싶어요") == "billing"


def test_tech_keyword_routes_to_tech():
    assert routing.keyword_route("로그인하면 자꾸 오류가 나고 접속이 안돼요") == "tech"


def test_sales_keyword_routes_to_sales():
    assert routing.keyword_route("신규 도입 견적 상담 받고 싶습니다") == "sales"


def test_unknown_defaults_to_general():
    assert routing.keyword_route("그냥 안부 전화했어요") == "general"


def test_priority_urgent():
    assert routing.estimate_priority("지금 서비스 전체가 먹통이라 긴급합니다") == "urgent"


def test_priority_normal_default():
    assert routing.estimate_priority("문의가 있어서요") == "normal"


def test_normalize_invalid_team_key():
    assert routing.normalize_team_key("not-a-team") == "general"
    assert routing.normalize_team_key("billing") == "billing"
    assert routing.normalize_team_key(None) == "general"
