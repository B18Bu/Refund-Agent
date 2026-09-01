"""Node A 确定性意图过滤测试（工单 8 任务二）。"""


def test_strong_signal_bypasses_llm():
    from app.agents.intent import IntentFilter

    result = IntentFilter().classify("这批订单都是刷单的，要求退款不掉货")

    assert result.route == "strong_signal"
    assert result.deterministic_fraud == 88
    assert result.deterministic_sentiment == "HIGH"
    assert "malicious" == result.label


def test_normal_complaint_routes_to_llm():
    from app.agents.intent import IntentFilter

    result = IntentFilter().classify("我收到的商品有质量问题，希望商家给个说法")

    assert result.route == "llm_judge"
    assert result.deterministic_fraud is None


def test_legitimate_refund_not_misclassified():
    from app.agents.intent import IntentFilter

    result = IntentFilter().classify("订单号 800123，申请金额 128 元，商品破损申请退款")

    assert result.route == "llm_judge"
    assert result.label == "refund_request"


def test_strong_signal_decision_still_deterministic():
    from app.agents.decision_rules import decide
    from app.agents.intent import IntentFilter

    result = IntentFilter().classify("恶意套现，伪造凭证申请退款")

    assert result.route == "strong_signal"
    route = decide(
        amount=128.0,
        ocr_confidence=0.95,
        fraud_score=int(result.deterministic_fraud or 0),
        sentiment=str(result.deterministic_sentiment or "HIGH"),
        ocr_text="订单号 800123 金额 128 元",
    )

    assert route == "HUMAN_REVIEW"
