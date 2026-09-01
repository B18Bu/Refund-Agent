from app.agents.decision_rules import (
    audit_evidence,
    decide,
    decide_with_reasons,
    extract_order_number,
    extract_refund_amounts,
    management_suggestion,
)


def test_extract_refund_amounts_from_ocr_text():
    amounts = extract_refund_amounts("破损商品退款申请\n金额350.00元")

    assert amounts == ["350.00"]


def test_extract_amount_from_order_number_with_yuan():
    """「订单号128元」语义明确是金额，应被识别为 128.00。"""
    amounts = extract_refund_amounts("正品全新商品+\n订单号128元")

    assert amounts == ["128.00"]


def test_extract_amount_from_currency_symbol_prefix():
    amounts = extract_refund_amounts("实付 ¥99.9")

    assert amounts == ["99.90"]


def test_plain_order_number_without_yuan_is_not_amount():
    """纯订单号（无货币单位）不得误判为金额。"""
    amounts = extract_refund_amounts("订单号 800123 日期 2026-08-31")

    assert amounts == []


def test_extract_order_number_from_ocr():
    assert extract_order_number("商品图片\n订单号 800123") == "800123"
    assert extract_order_number("订单编号：NO20260831A") == "NO20260831A"
    assert extract_order_number("破损商品退款申请\n金额350.00元") is None


def test_audit_evidence_three_dimensions():
    audit = audit_evidence(128.0, "正品全新商品+\n订单号128元")

    assert audit["price_consistency"] == "match"
    assert audit["order_authenticity"] == "pass"
    assert audit["goods_consistency"] == "pass"


def test_audit_evidence_mismatch_and_unverified():
    mismatch = audit_evidence(128.0, "破损商品退款申请\n金额350.00元")
    empty = audit_evidence(128.0, "")

    assert mismatch["price_consistency"] == "mismatch"
    assert mismatch["order_authenticity"] == "unverified"
    assert mismatch["goods_consistency"] == "pass"
    assert empty["price_consistency"] == "missing"
    assert empty["order_authenticity"] == "unverified"
    assert empty["goods_consistency"] == "unverified"


def test_management_suggestion_maps_first_blocking_reason():
    assert management_suggestion("AUTO_REFUND", []) == "建议自动退赔：金额/订单/商品校验一致且风险为低"
    assert "注入/越狱风险" in management_suggestion("HUMAN_REVIEW", ["security_injection_detected"])
    assert "动作层策略" in management_suggestion("HUMAN_REVIEW", ["action_policy_denied"])
    assert "复核价格" in management_suggestion("HUMAN_REVIEW", ["ocr_amount_mismatch"])
    assert "未识别到可核对金额" in management_suggestion("HUMAN_REVIEW", ["ocr_amount_missing"])
    assert "超过自动退赔上限" in management_suggestion("HUMAN_REVIEW", ["amount_over_limit"])


def test_human_review_when_ocr_amount_conflicts_with_application():
    result = decide_with_reasons(
        128.0,
        0.9971,
        20,
        "LOW",
        ocr_text="破损商品退款申请\n金额350.00元",
    )

    assert result.route == "HUMAN_REVIEW"
    assert result.reasons == ["ocr_amount_mismatch"]


def test_security_injection_is_highest_priority_red_line():
    result = decide_with_reasons(
        128.0,
        0.9987,
        20,
        "LOW",
        ocr_text="金额128.00元",
        security_risk=0.9,
    )

    assert result.route == "HUMAN_REVIEW"
    assert result.reasons == ["security_injection_detected"]


def test_security_risk_below_threshold_does_not_block():
    result = decide_with_reasons(
        128.0,
        0.9987,
        20,
        "LOW",
        ocr_text="金额128.00元",
        security_risk=0.8,
    )

    assert result.route == "AUTO_REFUND"


def test_human_review_when_ocr_amount_missing():
    result = decide_with_reasons(
        128.0,
        0.9971,
        20,
        "LOW",
        ocr_text="破损商品退款申请，请尽快处理",
    )

    assert result.route == "HUMAN_REVIEW"
    assert result.reasons == ["ocr_amount_missing"]


def test_auto_refund_when_amount_appears_as_order_number_with_yuan():
    """凭证写「订单号128元」且与申请金额一致 → 自动退赔。"""
    result = decide_with_reasons(
        128.0,
        0.9987,
        20,
        "LOW",
        ocr_text="正品全新商品+\n订单号128元",
    )

    assert result.route == "AUTO_REFUND"
    assert "ocr_amount_match" in result.reasons


def test_decision_reasons_explain_auto_refund():
    result = decide_with_reasons(128.0, 0.95, 20, "LOW", ocr_text="金额128.00元")

    assert result.route == "AUTO_REFUND"
    assert result.reasons == [
        "amount_within_limit",
        "ocr_confidence_pass",
        "ocr_amount_match",
        "fraud_pass",
        "sentiment_low",
    ]


def test_decision_reasons_explain_first_blocking_rule():
    result = decide_with_reasons(128.0, 0.95, 80, "HIGH")

    assert result.route == "HUMAN_REVIEW"
    assert result.reasons == ["fraud_score_at_threshold"]


def test_auto_refund_low_risk():
    assert decide(128.0, 0.95, 20, "LOW", ocr_text="金额128.00元") == "AUTO_REFUND"


def test_human_review_over_limit():
    assert decide(350.0, 0.95, 20, "LOW") == "HUMAN_REVIEW"


def test_human_review_low_ocr_confidence():
    assert decide(128.0, 0.3, 20, "LOW") == "HUMAN_REVIEW"


def test_human_review_high_fraud():
    assert decide(128.0, 0.95, 80, "LOW") == "HUMAN_REVIEW"


def test_human_review_high_sentiment():
    assert decide(128.0, 0.95, 20, "HIGH") == "HUMAN_REVIEW"


def test_human_review_high_fraud_high_sentiment():
    assert decide(128.0, 0.95, 80, "HIGH") == "HUMAN_REVIEW"


def test_boundary_amount_equals_max_still_auto():
    # 边界：金额=300 恰为上限（>300 才触发人工）
    assert decide(300.0, 0.95, 20, "LOW", ocr_text="金额300.00元") == "AUTO_REFUND"


def test_boundary_ocr_confidence_equals_threshold():
    # 边界：置信度=0.60 恰为阈值（<0.60 才触发人工）
    assert decide(128.0, 0.60, 20, "LOW", ocr_text="金额128.00元") == "AUTO_REFUND"


def test_boundary_fraud_equals_threshold():
    # 边界：欺诈=50 恰为阈值（>=50 触发人工）
    assert decide(128.0, 0.95, 50, "LOW") == "HUMAN_REVIEW"
