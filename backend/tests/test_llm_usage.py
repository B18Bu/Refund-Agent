from types import SimpleNamespace


def test_provider_usage_is_preferred(monkeypatch):
    from app.agents import llm

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"fraud_score": 21}'))],
        usage=SimpleNamespace(prompt_tokens=40, completion_tokens=6, total_tokens=46),
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_: response),
        )
    )
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(llm, "get_client", lambda: fake_client)

    value, usage = llm.LlmRiskClient().score_fraud_with_usage("材料")

    assert value == 21
    assert usage.input_tokens == 40
    assert usage.output_tokens == 6
    assert usage.total_tokens == 46
    assert usage.measurement_type == "actual"


def test_mock_usage_is_marked_estimated(monkeypatch):
    from app.agents import llm

    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "mock")
    value, usage = llm.LlmRiskClient().classify_sentiment_with_usage("普通客诉")

    assert value == "LOW"
    assert usage.input_tokens > 0
    assert usage.total_tokens >= usage.input_tokens
    assert usage.measurement_type == "estimated"


def test_nodes_propagate_usage_and_latency(monkeypatch):
    from app.agents import nodes
    from app.agents.llm import UsageSnapshot

    class FakeRisk:
        def score_fraud_with_usage(self, _):
            return 21, UsageSnapshot(10, 2, 12, "actual")

        def classify_sentiment_with_usage(self, _):
            return "LOW", UsageSnapshot(8, 1, 9, "actual")

    monkeypatch.setattr(nodes, "_risk_client", FakeRisk())
    state = {"amount": 128.0, "ocr_text": "清晰商品图"}

    nodes.fraud_node(state)
    nodes.sentiment_node(state)

    assert state["fraud_score"] == 21
    assert state["sentiment"] == "LOW"
    assert state["token_usage"]["fraud"]["total_tokens"] == 12
    assert state["token_usage"]["sentiment"]["total_tokens"] == 9
    assert state["latency_breakdown"]["fraud_ms"] >= 0
    assert state["latency_breakdown"]["sentiment_ms"] >= 0
