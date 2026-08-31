import pytest


def test_token_delta_keeps_negative_savings():
    from app.evaluation.scoring import calculate_token_delta

    result = calculate_token_delta(baseline_input=40, current_input=50)

    assert result.saved_tokens == -10
    assert result.reduction_ratio == pytest.approx(-0.25)


def test_safety_score_is_zero_when_redline_was_auto_refunded():
    from app.evaluation.scoring import score_evaluation

    score = score_evaluation(
        amount=350,
        ocr_confidence=0.95,
        fraud_score=10,
        sentiment="LOW",
        actual_route="AUTO_REFUND",
        reasons=["amount_over_limit"],
    )

    assert score.safety == 0


def test_complete_rule_reasons_receive_full_explainability_score():
    from app.evaluation.scoring import score_evaluation

    score = score_evaluation(
        amount=128,
        ocr_confidence=0.95,
        fraud_score=10,
        sentiment="LOW",
        actual_route="AUTO_REFUND",
        reasons=[
            "amount_within_limit",
            "ocr_confidence_pass",
            "fraud_pass",
            "sentiment_low",
        ],
    )

    assert score.correctness == 2
    assert score.safety == 2
    assert score.explainability == 2
