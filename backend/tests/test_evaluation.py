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


def test_llm_judge_skipped_when_mock(monkeypatch):
    from app.evaluation import judge

    monkeypatch.setattr(judge.settings, "LLM_PROVIDER", "mock")

    assert judge.judge_case({"case_id": "G01"}, "AUTO_REFUND") is None


def test_llm_judge_parses_json_response(monkeypatch):
    from app.evaluation import judge

    class FakeCompletions:
        def create(self, **kwargs):
            class _Msg:
                content = '{"correctness":2,"safety":2,"explainability":1,"verdict":"pass","rationale":"规则一致"}'

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(judge.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(judge, "get_client", lambda: FakeClient())

    result = judge.judge_case({"case_id": "G01"}, "AUTO_REFUND")

    assert result is not None
    assert result["correctness"] == 2
    assert result["safety"] == 2
    assert result["verdict"] == "pass"


def test_llm_judge_failure_returns_none(monkeypatch):
    from app.evaluation import judge

    def boom(**kwargs):
        raise RuntimeError("llm down")

    class FakeClient:
        chat = type("Chat", (), {"completions": type("C", (), {"create": staticmethod(boom)})()})()

    monkeypatch.setattr(judge.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(judge, "get_client", lambda: FakeClient())

    assert judge.judge_case({"case_id": "G01"}, "AUTO_REFUND") is None
