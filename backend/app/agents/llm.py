"""LLM/风控适配器：OpenAI 兼容客户端，可切换 DeepSeek 与本地 Mock/Stub。

三方对齐：
- DeepSeek（`deepseek-chat`，OpenAI 兼容接口）。
- `LLM_PROVIDER=mock` 时走确定性 Stub，供本地无密钥/单测使用。
- 失败兜底：LLM 调用异常 → 保守值（fraud=100 / sentiment=HIGH）→ 决策层强制 HUMAN_REVIEW，绝不自动放行。
"""
import json
import logging
from typing import Literal

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

_client: OpenAI | None = None


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
        if settings.LLM_PROVIDER == "mock":
            return _mock_fraud_score(material)
        client = get_client()
        if client is None:
            return 100
        try:
            system = "你是电商退款风控专家。只输出 JSON，禁止其它文字。"
            prompt = (
                "根据以下凭证 OCR 文本与退款金额，评估恶意退款/薅羊毛欺诈分"
                "（0-100 整数，越高越可疑）。\n只输出 JSON："
                '{"fraud_score": <int>}\n材料：' + material
            )
            raw = self._chat(system, prompt)
            score = int(json.loads(raw).get("fraud_score", 100))
            return max(0, min(100, score))
        except Exception as exc:  # 兜底：宁挂勿错退
            logger.warning("fraud LLM 失败，兜底 100: %s", exc)
            return 100

    def classify_sentiment(self, material: str) -> RiskLevel:
        """舆情等级 LOW/MEDIUM/HIGH。失败兜底 HIGH。"""
        if settings.LLM_PROVIDER == "mock":
            return _mock_sentiment(material)
        client = get_client()
        if client is None:
            return "HIGH"
        try:
            system = "你是舆情分析专家。只输出 LOW / MEDIUM / HIGH 之一，禁止其它文字。"
            prompt = "根据以下客诉内容评估舆情等级：\n" + material
            raw = self._chat(system, prompt).strip().upper()
            if raw not in ("LOW", "MEDIUM", "HIGH"):
                return "HIGH"
            return raw  # type: ignore[return-value]
        except Exception as exc:
            logger.warning("sentiment LLM 失败，兜底 HIGH: %s", exc)
            return "HIGH"

    def _chat(self, system: str, user: str) -> str:
        client = get_client()
        assert client is not None
        resp = client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            timeout=30,
        )
        return resp.choices[0].message.content or ""


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
