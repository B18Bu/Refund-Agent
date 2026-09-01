import asyncio


def test_parallel_risk_keeps_success_when_one_tool_fails():
    from app.agents.llm import score_risk_parallel

    class FakeRisk:
        async def score_fraud_async(self, _):
            return 21

        async def classify_sentiment_async(self, _):
            raise RuntimeError("sentiment timeout")

    fraud, sentiment = asyncio.run(score_risk_parallel(FakeRisk(), "材料"))

    assert fraud == 21
    assert sentiment == "HIGH"


def test_parallel_risk_maps_fraud_failure_to_conservative_score():
    from app.agents.llm import score_risk_parallel

    class FakeRisk:
        async def score_fraud_async(self, _):
            raise RuntimeError("fraud timeout")

        async def classify_sentiment_async(self, _):
            return "LOW"

    fraud, sentiment = asyncio.run(score_risk_parallel(FakeRisk(), "材料"))

    assert fraud == 100
    assert sentiment == "LOW"


def test_parallel_risk_with_usage_preserves_actual_usage():
    from app.agents.llm import UsageSnapshot, score_risk_parallel_with_usage

    class FakeRisk:
        def score_fraud_with_usage(self, _):
            return 21, UsageSnapshot(10, 5, 15, "actual")

        def classify_sentiment_with_usage(self, _):
            return "LOW", UsageSnapshot(8, 3, 11, "actual")

    fraud, sentiment, fraud_usage, sentiment_usage, fraud_ms, sentiment_ms = asyncio.run(
        score_risk_parallel_with_usage(FakeRisk(), "材料")
    )

    assert fraud == 21
    assert sentiment == "LOW"
    assert fraud_usage.measurement_type == "actual"
    assert fraud_usage.total_tokens == 15
    assert sentiment_usage.total_tokens == 11
    assert fraud_ms >= 0
    assert sentiment_ms >= 0


def test_parallel_risk_with_usage_falls_back_conservatively_on_failure():
    from app.agents.llm import UsageSnapshot, score_risk_parallel_with_usage

    class FakeRisk:
        def score_fraud_with_usage(self, _):
            return 21, UsageSnapshot(10, 5, 15, "actual")

        def classify_sentiment_with_usage(self, _):
            raise RuntimeError("sentiment timeout")

    fraud, sentiment, fraud_usage, sentiment_usage, _, _ = asyncio.run(
        score_risk_parallel_with_usage(FakeRisk(), "材料")
    )

    assert fraud == 21
    assert sentiment == "HIGH"
    assert fraud_usage.measurement_type == "actual"
    assert sentiment_usage.measurement_type == "estimated"
