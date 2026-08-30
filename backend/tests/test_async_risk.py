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

