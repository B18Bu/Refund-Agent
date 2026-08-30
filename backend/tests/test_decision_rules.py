from app.agents.decision_rules import decide, decide_with_reasons


def test_decision_reasons_explain_auto_refund():
    result = decide_with_reasons(128.0, 0.95, 20, "LOW")

    assert result.route == "AUTO_REFUND"
    assert result.reasons == [
        "amount_within_limit",
        "ocr_confidence_pass",
        "fraud_pass",
        "sentiment_low",
    ]


def test_decision_reasons_explain_first_blocking_rule():
    result = decide_with_reasons(128.0, 0.95, 80, "HIGH")

    assert result.route == "HUMAN_REVIEW"
    assert result.reasons == ["fraud_score_at_threshold"]


def test_auto_refund_low_risk():
    assert decide(128.0, 0.95, 20, "LOW") == "AUTO_REFUND"


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
    assert decide(300.0, 0.95, 20, "LOW") == "AUTO_REFUND"


def test_boundary_ocr_confidence_equals_threshold():
    # 边界：置信度=0.60 恰为阈值（<0.60 才触发人工）
    assert decide(128.0, 0.60, 20, "LOW") == "AUTO_REFUND"


def test_boundary_fraud_equals_threshold():
    # 边界：欺诈=50 恰为阈值（>=50 触发人工）
    assert decide(128.0, 0.95, 50, "LOW") == "HUMAN_REVIEW"
