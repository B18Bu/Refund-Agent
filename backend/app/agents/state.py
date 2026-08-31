"""LangGraph 图状态。"""
from typing import TypedDict


class GraphState(TypedDict, total=False):
    ticket_id: str
    amount: float
    image_paths: list[str]
    ocr_text: str
    ocr_confidence: float
    fraud_score: int
    sentiment: str
    decision: str          # AUTO_REFUND / HUMAN_REVIEW
    decision_reasons: list[str]
    final_decision: str    # PENDING / AUTO_REFUNDED / APPROVED / REJECTED
    approval_action: str   # APPROVE / REJECT（主管输入）
    token_usage: dict[str, dict[str, int | str]]
    latency_breakdown: dict[str, float]
