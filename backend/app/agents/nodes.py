"""LangGraph 决策流节点。

职责边界：节点只做「调 OCR/LLM + 组装 state」，业务判断全部下沉到 `decision_rules.decide`。
挂起采用 LangGraph 原生 `interrupt()`（三方对齐：禁止手工 pickle）。
"""
from langgraph.types import interrupt

from app.agents.decision_rules import decide
from app.agents.llm import LlmRiskClient
from app.agents.ocr import OcrClient
from app.agents.state import GraphState
from app.storage import resolve_abs_path

_risk_client = LlmRiskClient()
_ocr_client = OcrClient()


def intake(state: GraphState) -> GraphState:
    state["ocr_text"] = ""
    state["ocr_confidence"] = 0.0
    state["fraud_score"] = 0
    state["sentiment"] = "LOW"
    state["final_decision"] = "PENDING"
    return state


def ocr_node(state: GraphState) -> GraphState:
    paths = state.get("image_paths", [])
    texts, scores = [], []
    for p in paths:
        image_path = resolve_abs_path(p) if p.startswith(("uploads/", "uploads\\")) else p
        r = _ocr_client.extract(image_path)
        texts.append(r.text)
        scores.append(r.confidence)
    state["ocr_text"] = "\n".join(texts)
    # 多图取最小置信度（木桶原则）；无图/识别失败 → 0
    state["ocr_confidence"] = min(scores) if scores else 0.0
    return state


def fraud_node(state: GraphState) -> GraphState:
    material = f"退款金额：{state.get('amount')}\n凭证 OCR：{state.get('ocr_text', '')}"
    state["fraud_score"] = _risk_client.score_fraud(material)
    return state


def sentiment_node(state: GraphState) -> GraphState:
    material = state.get("ocr_text", "") or f"客诉金额：{state.get('amount')}"
    state["sentiment"] = _risk_client.classify_sentiment(material)
    return state


def decision_node(state: GraphState) -> GraphState:
    d = decide(
        float(state["amount"]),
        float(state.get("ocr_confidence", 0.0)),
        int(state.get("fraud_score", 0)),
        str(state.get("sentiment", "LOW")),
    )
    state["decision"] = d
    if d == "AUTO_REFUND":
        state["final_decision"] = "AUTO_REFUNDED"
    return state


def route_after_decision(state: GraphState) -> str:
    return state["decision"]


def human_review_node(state: GraphState) -> GraphState:
    """人工审批节点：interrupt() 挂起，等待主管 Command(resume={"action": ...})。"""
    resp = interrupt({"ticket_id": state.get("ticket_id"), "message": "需要人工审批"})
    action = resp["action"]
    state["approval_action"] = action
    state["final_decision"] = "APPROVED" if action == "APPROVE" else "REJECTED"
    return state
