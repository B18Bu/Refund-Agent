"""Node A 确定性意图过滤（工单 8）。

职责边界：只做“过滤/分流”，不改变 decision_rules 的确定性路由语义；
命中强信号时写入确定性欺诈分/舆情（仍由 decision 层按原阈值裁决）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.agents.llm import RiskLevel

IntentRoute = Literal["strong_signal", "llm_judge"]
IntentLabel = Literal["refund_request", "complaint", "malicious", "general"]

# 强信号关键词：黑产/恶意信号，命中即跳过 LLM（复用 _mock_fraud_score 词表并扩展）
_STRONG_KEYWORDS = (
    "恶意", "黑产", "套现", "刷单", "批量", "薅羊毛", "退款不掉货",
    "洗钱", "伪造凭证", "ps凭证", "ps 凭证", "假图", "虚构订单",
)
_REFUND_KEYWORDS = ("退款", "退货", "退钱", "退换", "退回", "退赔", "赔偿", "赔付")
_COMPLAINT_KEYWORDS = ("投诉", "曝光", "维权", "愤怒", "黑猫")


@dataclass(frozen=True)
class IntentResult:
    route: IntentRoute
    label: IntentLabel
    hit_rules: list[str]
    deterministic_fraud: int | None = None
    deterministic_sentiment: RiskLevel | None = None


class IntentFilter:
    """Node A：确定性意图过滤与分流。"""

    def classify(self, text: str) -> IntentResult:
        content = (text or "").lower()
        for keyword in _STRONG_KEYWORDS:
            if keyword in content:
                return IntentResult(
                    route="strong_signal",
                    label="malicious",
                    hit_rules=["strong_signal_keyword"],
                    deterministic_fraud=88,
                    deterministic_sentiment="HIGH",
                )
        for keyword in _REFUND_KEYWORDS:
            if keyword in content:
                return IntentResult(route="llm_judge", label="refund_request", hit_rules=[])
        for keyword in _COMPLAINT_KEYWORDS:
            if keyword in content:
                return IntentResult(route="llm_judge", label="complaint", hit_rules=[])
        return IntentResult(route="llm_judge", label="general", hit_rules=[])
