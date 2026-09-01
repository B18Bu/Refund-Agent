"""LLM/风控适配器：OpenAI 兼容客户端，可切换 DeepSeek 与本地 Mock/Stub。

三方对齐：
- DeepSeek（`deepseek-chat`，OpenAI 兼容接口）。
- `LLM_PROVIDER=mock` 时走确定性 Stub，供本地无密钥/单测使用。
- 失败兜底：LLM 调用异常 → 保守值（fraud=100 / sentiment=HIGH）→ 决策层强制 HUMAN_REVIEW，绝不自动放行。
"""
import json
import logging
import asyncio
import time
from dataclasses import asdict, dataclass
from typing import Literal

from openai import OpenAI

from app.config import settings
from app.agents.prompts import (
    FRAUD_SYSTEM_PROMPT,
    SENTIMENT_SYSTEM_PROMPT,
    estimate_prompt_tokens,
    optimized_prompt,
    sentiment_prompt,
)

logger = logging.getLogger(__name__)

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

_client: OpenAI | None = None


@dataclass(frozen=True)
class UsageSnapshot:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    measurement_type: str

    def as_dict(self) -> dict[str, int | str]:
        return asdict(self)


def _estimated_usage(input_text: str, output_text: str) -> UsageSnapshot:
    input_tokens = estimate_prompt_tokens(input_text)
    output_tokens = estimate_prompt_tokens(output_text)
    return UsageSnapshot(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        measurement_type="estimated",
    )


def retry_call(fn, *, attempts: int = 3, base_delay: float = 1.0, sleep_fn=time.sleep):
    """指数退避重试：attempts=首次+重试次数，退避 base_delay*2^attempt。

    sleep_fn 可注入（测试用 0 延迟）；重试仍失败时抛出最后一次异常。
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                sleep_fn(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc


def get_client() -> OpenAI | None:
    """惰性创建 OpenAI 兼容客户端；Mock 模式返回 None。"""
    global _client
    if settings.LLM_PROVIDER == "mock":
        return None
    if _client is None:
        _client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    return _client


class LlmRiskClient:
    """风控/舆情分析客户端（可替换适配器）。"""

    def score_fraud(self, material: str) -> int:
        """欺诈分 0-100 整数，越高越可疑。失败兜底 100。"""
        return self.score_fraud_with_usage(material)[0]

    def score_fraud_with_usage(self, material: str) -> tuple[int, UsageSnapshot]:
        value, usage, _reason = self.score_fraud_with_usage_and_reason(material)
        return value, usage

    def score_fraud_with_usage_and_reason(
        self, material: str
    ) -> tuple[int, UsageSnapshot, str | None]:
        """返回 (分数, usage, fallback_reason | None)，失败原因显式可审计。"""
        user_prompt = optimized_prompt(material)
        system = FRAUD_SYSTEM_PROMPT
        if settings.LLM_PROVIDER == "mock":
            value = _mock_fraud_score(material)
            return value, _estimated_usage(f"{system}\n{user_prompt}", str(value)), None
        client = get_client()
        if client is None:
            return 100, _estimated_usage(f"{system}\n{user_prompt}", "100"), "llm_call_failed"
        try:
            raw, usage = self._chat_with_usage(system, user_prompt)
        except Exception as exc:  # 调用失败时没有供应商 usage，只能离线估算
            logger.warning("fraud LLM 调用失败，兜底 100: %s", exc)
            return 100, _estimated_usage(f"{system}\n{user_prompt}", "100"), "llm_call_failed"
        try:
            score = int(json.loads(raw).get("fraud_score", 100))
            return max(0, min(100, score)), usage, None
        except (TypeError, ValueError, json.JSONDecodeError) as exc:  # 解析失败仍保留真实 usage
            logger.warning("fraud LLM 响应解析失败，兜底 100: %s", exc)
            return 100, usage, "llm_output_parse_fallback"

    def classify_sentiment(self, material: str) -> RiskLevel:
        """舆情等级 LOW/MEDIUM/HIGH。失败兜底 HIGH。"""
        return self.classify_sentiment_with_usage(material)[0]

    def classify_sentiment_with_usage(self, material: str) -> tuple[RiskLevel, UsageSnapshot]:
        value, usage, _reason = self.classify_sentiment_with_usage_and_reason(material)
        return value, usage

    def classify_sentiment_with_usage_and_reason(
        self, material: str
    ) -> tuple[RiskLevel, UsageSnapshot, str | None]:
        """返回 (等级, usage, fallback_reason | None)，失败原因显式可审计。"""
        system = SENTIMENT_SYSTEM_PROMPT
        prompt = sentiment_prompt(material)
        if settings.LLM_PROVIDER == "mock":
            value = _mock_sentiment(material)
            return value, _estimated_usage(f"{system}\n{prompt}", value), None
        client = get_client()
        if client is None:
            return "HIGH", _estimated_usage(f"{system}\n{prompt}", "HIGH"), "llm_call_failed"
        try:
            response, usage = self._chat_with_usage(system, prompt)
            raw = response.strip().upper()
            if raw not in ("LOW", "MEDIUM", "HIGH"):
                return "HIGH", usage, "llm_output_parse_fallback"
            return raw, usage, None  # type: ignore[return-value]
        except Exception as exc:
            logger.warning("sentiment LLM 失败，兜底 HIGH: %s", exc)
            return "HIGH", _estimated_usage(f"{system}\n{prompt}", "HIGH"), "llm_call_failed"

    def _chat(self, system: str, user: str) -> str:
        return self._chat_with_usage(system, user)[0]

    def _chat_with_usage(self, system: str, user: str) -> tuple[str, UsageSnapshot]:
        client = get_client()
        assert client is not None
        resp = retry_call(
            lambda: client.chat.completions.create(
                model=settings.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                timeout=30,
            ),
            attempts=settings.LLM_RETRY_MAX_ATTEMPTS,
            base_delay=settings.LLM_RETRY_BASE_DELAY_SECONDS,
        )
        content = resp.choices[0].message.content or ""
        provider_usage = getattr(resp, "usage", None)
        input_tokens = getattr(provider_usage, "prompt_tokens", None)
        output_tokens = getattr(provider_usage, "completion_tokens", None)
        total_tokens = getattr(provider_usage, "total_tokens", None)
        if input_tokens is None or output_tokens is None:
            return content, _estimated_usage(f"{system}\n{user}", content)
        return content, UsageSnapshot(
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            total_tokens=int(total_tokens or (input_tokens + output_tokens)),
            measurement_type="actual",
        )

    async def score_fraud_async(self, material: str) -> int:
        """在线程池执行同步客户端，避免阻塞事件循环。"""
        return await asyncio.to_thread(self.score_fraud, material)

    async def classify_sentiment_async(self, material: str) -> RiskLevel:
        """在线程池执行同步客户端，避免阻塞事件循环。"""
        return await asyncio.to_thread(self.classify_sentiment, material)


async def score_risk_parallel(client: LlmRiskClient, material: str) -> tuple[int, RiskLevel]:
    """并行执行欺诈和舆情分析，单项异常不会取消另一项。"""
    fraud, sentiment = await asyncio.gather(
        client.score_fraud_async(material),
        client.classify_sentiment_async(material),
        return_exceptions=True,
    )
    fraud_value = 100 if isinstance(fraud, Exception) else max(0, min(100, int(fraud)))
    sentiment_value: RiskLevel = "HIGH" if isinstance(sentiment, Exception) else (
        sentiment if sentiment in ("LOW", "MEDIUM", "HIGH") else "HIGH"
    )
    return fraud_value, sentiment_value


def _timed_sync(fn, *args):
    """同步调用并返回 (结果, 耗时毫秒)。"""
    started_at = time.perf_counter()
    result = fn(*args)
    return result, (time.perf_counter() - started_at) * 1000


async def score_risk_parallel_with_usage(
    client: LlmRiskClient, material: str
) -> tuple[int, RiskLevel, UsageSnapshot, UsageSnapshot, float, float]:
    """并行执行欺诈/舆情并保留各自 usage 与耗时；单项异常保守兜底，不取消另一项。"""
    fraud_future = asyncio.to_thread(_timed_sync, client.score_fraud_with_usage, material)
    sentiment_future = asyncio.to_thread(_timed_sync, client.classify_sentiment_with_usage, material)
    fraud_res, sentiment_res = await asyncio.gather(fraud_future, sentiment_future, return_exceptions=True)

    fraud_value = 100
    fraud_usage = _estimated_usage(f"fraud:{material}", "100")
    fraud_ms = 0.0
    if not isinstance(fraud_res, Exception):
        (value, usage), fraud_ms = fraud_res
        fraud_value = max(0, min(100, int(value)))
        fraud_usage = usage

    sentiment_value: RiskLevel = "HIGH"
    sentiment_usage = _estimated_usage(f"sentiment:{material}", "HIGH")
    sentiment_ms = 0.0
    if not isinstance(sentiment_res, Exception):
        (value, usage), sentiment_ms = sentiment_res
        sentiment_value = value if value in ("LOW", "MEDIUM", "HIGH") else "HIGH"
        sentiment_usage = usage

    return fraud_value, sentiment_value, fraud_usage, sentiment_usage, fraud_ms, sentiment_ms


async def score_risk_parallel_with_usage_and_fallbacks(
    client: LlmRiskClient, material: str
) -> tuple[int, RiskLevel, UsageSnapshot, UsageSnapshot, float, float, list[str]]:
    """并行执行欺诈/舆情并保留 usage/耗时/显式兜底原因（工单 8）。"""
    fraud_future = asyncio.to_thread(_timed_sync, client.score_fraud_with_usage_and_reason, material)
    sentiment_future = asyncio.to_thread(_timed_sync, client.classify_sentiment_with_usage_and_reason, material)
    fraud_res, sentiment_res = await asyncio.gather(fraud_future, sentiment_future, return_exceptions=True)

    fallback_reasons: list[str] = []
    fraud_value = 100
    fraud_usage = _estimated_usage(f"fraud:{material}", "100")
    fraud_ms = 0.0
    if not isinstance(fraud_res, Exception):
        (value, usage, reason), fraud_ms = fraud_res
        fraud_value = max(0, min(100, int(value)))
        fraud_usage = usage
        if reason:
            fallback_reasons.append(reason)
    else:
        fallback_reasons.append("llm_call_failed")

    sentiment_value: RiskLevel = "HIGH"
    sentiment_usage = _estimated_usage(f"sentiment:{material}", "HIGH")
    sentiment_ms = 0.0
    if not isinstance(sentiment_res, Exception):
        (value, usage, reason), sentiment_ms = sentiment_res
        sentiment_value = value if value in ("LOW", "MEDIUM", "HIGH") else "HIGH"
        sentiment_usage = usage
        if reason:
            fallback_reasons.append(reason)
    else:
        fallback_reasons.append("llm_call_failed")

    return (
        fraud_value,
        sentiment_value,
        fraud_usage,
        sentiment_usage,
        fraud_ms,
        sentiment_ms,
        fallback_reasons,
    )


def _mock_fraud_score(material: str) -> int:
    """确定性 Stub：包含异常关键词时给高分，否则按材料长度小幅波动（保证稳定）。"""
    text = (material or "").lower()
    if any(k in text for k in ("恶意", "黑产", "套现", "刷单", "批量", "薅羊毛", "退款不掉货")):
        return 88
    return 20


def _mock_sentiment(material: str) -> RiskLevel:
    text = (material or "").lower()
    if any(k in text for k in ("投诉", "曝光", "愤怒", "维权", "黑猫", "抖音", "骂", "气")):
        return "HIGH"
    if any(k in text for k in ("不满", "失望", "吐槽", "差评")):
        return "MEDIUM"
    return "LOW"
