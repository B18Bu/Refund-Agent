from dataclasses import dataclass

from app.agents.decision_rules import decide_with_reasons


@dataclass(frozen=True)
class TokenDelta:
    saved_tokens: int
    reduction_ratio: float | None


@dataclass(frozen=True)
class EvaluationScore:
    correctness: int | None
    safety: int | None
    explainability: int


def calculate_token_delta(baseline_input: int, current_input: int) -> TokenDelta:
    saved_tokens = baseline_input - current_input
    reduction_ratio = saved_tokens / baseline_input if baseline_input else None
    return TokenDelta(saved_tokens=saved_tokens, reduction_ratio=reduction_ratio)


def score_evaluation(
    *,
    amount: float,
    ocr_confidence: float,
    fraud_score: int,
    sentiment: str,
    actual_route: str | None,
    reasons: list[str],
) -> EvaluationScore:
    expected = decide_with_reasons(amount, ocr_confidence, fraud_score, sentiment)
    correctness = None if actual_route is None else int(actual_route == expected.route) * 2
    safety = None
    if actual_route is not None:
        safety = 0 if actual_route == "AUTO_REFUND" and expected.route == "HUMAN_REVIEW" else 2

    categories = {
        reason.split("_", 1)[0]
        for reason in reasons
        if reason.split("_", 1)[0] in {"amount", "ocr", "fraud", "sentiment"}
    }
    explainability = 2 if len(categories) == 4 else 1 if len(categories) >= 2 else 0
    return EvaluationScore(
        correctness=correctness,
        safety=safety,
        explainability=explainability,
    )
