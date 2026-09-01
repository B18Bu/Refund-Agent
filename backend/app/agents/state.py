"""LangGraph 图状态。"""
from typing import TypedDict


class GraphState(TypedDict, total=False):
    ticket_id: str
    trace_id: str
    amount: float
    image_paths: list[str]
    ocr_text: str
    ocr_confidence: float
    masked_ocr_text: str      # DLP 脱敏后的 OCR 文本（供 LLM/日志/观测）
    dlp_entities: list[str]
    critic_risk: float        # 注入/越狱风险分 0~1
    security_flags: list[str] # 命中规则
    intent_route: str         # strong_signal / llm_judge（Node A 分流）
    intent_label: str         # refund_request / complaint / malicious / general
    intent_hit_rules: list[str]
    fallback_reasons: list[str]  # llm_call_failed / llm_output_parse_fallback
    fraud_score: int
    sentiment: str
    decision: str          # AUTO_REFUND / HUMAN_REVIEW
    decision_reasons: list[str]
    evidence_audit: dict   # 价格一致性 / 订单真实性 / 商品一致性
    management_suggestion: str
    final_decision: str    # PENDING / AUTO_REFUNDED / APPROVED / REJECTED
    approval_action: str   # APPROVE / REJECT（主管输入）
    token_usage: dict[str, dict[str, int | str]]
    latency_breakdown: dict[str, float]
