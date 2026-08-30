from pathlib import Path


def test_golden_dataset_has_ten_valid_cases():
    from evals.schemas import load_golden_cases

    cases = load_golden_cases(Path("evals/golden/refund_cases.jsonl"))

    assert len(cases) == 10
    assert {case.case_id for case in cases} == {f"G{i:02d}" for i in range(1, 11)}
    assert all(case.expected_route in {"AUTO_REFUND", "HUMAN_REVIEW"} for case in cases)


def test_golden_cases_match_deterministic_policy():
    from app.agents.decision_rules import decide
    from evals.schemas import load_golden_cases

    cases = load_golden_cases(Path("evals/golden/refund_cases.jsonl"))

    for case in cases:
        actual = decide(case.amount, case.ocr_confidence, case.fraud_score, case.sentiment)
        assert actual == case.expected_route, case.case_id

