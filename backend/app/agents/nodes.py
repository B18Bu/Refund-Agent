"""LangGraph 决策流节点。

职责边界：节点只做「调 OCR/LLM + 组装 state」，业务判断全部下沉到 `decision_rules.decide`。
挂起采用 LangGraph 原生 `interrupt()`（三方对齐：禁止手工 pickle）。
"""
import time
import asyncio

from langgraph.types import interrupt

from app.agents.decision_rules import audit_evidence, decide_with_reasons, management_suggestion
from app.agents.intent import IntentFilter, IntentResult
from app.agents.llm import (
    LlmRiskClient,
    UsageSnapshot,
    score_risk_parallel_with_usage,
    score_risk_parallel_with_usage_and_fallbacks,
)
from app.agents.prompts import estimate_prompt_tokens
from app.agents.ocr import OcrClient
from app.config import settings
from app.security.action_policy import ActionPolicy, ActionRequest
from app.security.gateway import CriticEngine, DLP
from app.agents.state import GraphState
from app.storage import resolve_abs_path

_risk_client = LlmRiskClient()
_ocr_client = OcrClient()
_intent_filter = IntentFilter()
_action_policy = ActionPolicy()


def intake(state: GraphState) -> GraphState:
    state["ocr_text"] = ""
    state["ocr_confidence"] = 0.0
    state["fraud_score"] = 0
    state["sentiment"] = "LOW"
    state["final_decision"] = "PENDING"
    return state


def ocr_node(state: GraphState) -> GraphState:
    started_at = time.perf_counter()
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
    state.setdefault("latency_breakdown", {})["ocr_ms"] = (
        time.perf_counter() - started_at
    ) * 1000
    return state


def critic_node(state: GraphState) -> GraphState:
    """安全网关：对 OCR 文本做 DLP 脱敏 + Critic 注入/越狱检测。

    掩码文本存入 `masked_ocr_text` 供 LLM 与观测使用；检测用原文（掩码会破坏编码类变体）。
    命中阈值只影响决策（decision_node 依据 critic_risk 转人工），本节点不直接改路由。
    """
    started_at = time.perf_counter()
    ocr_text = state.get("ocr_text") or ""
    if settings.DLP_ENABLED:
        masked, entities = DLP.mask(ocr_text)
    else:
        masked, entities = ocr_text, []
    state["masked_ocr_text"] = masked
    state["dlp_entities"] = entities
    if settings.SECURITY_GATEWAY_ENABLED:
        risk, flags = CriticEngine().score(ocr_text)
        state["critic_risk"] = round(risk, 4)
        state["security_flags"] = flags
    else:
        state["critic_risk"] = 0.0
        state["security_flags"] = []
    state.setdefault("latency_breakdown", {})["critic_ms"] = (
        time.perf_counter() - started_at
    ) * 1000
    return state


def intent_node(state: GraphState) -> GraphState:
    """Node A：确定性意图过滤/分流。命中强信号 → 写入确定性分数并跳过 LLM。"""
    started_at = time.perf_counter()
    text = state.get("masked_ocr_text") or state.get("ocr_text", "")
    if settings.INTENT_FILTER_ENABLED:
        result = _intent_filter.classify(text)
    else:
        result = IntentResult(route="llm_judge", label="general", hit_rules=["intent_filter_disabled"])
    state["intent_route"] = result.route
    state["intent_label"] = result.label
    state["intent_hit_rules"] = result.hit_rules
    state.setdefault("fallback_reasons", [])
    if result.route == "strong_signal":
        state["fraud_score"] = int(result.deterministic_fraud or 0)
        state["sentiment"] = result.deterministic_sentiment or "HIGH"
    state.setdefault("latency_breakdown", {})["intent_ms"] = (
        time.perf_counter() - started_at
    ) * 1000
    return state


def route_intent(state: GraphState) -> str:
    return state.get("intent_route", "llm_judge")


def risk_node(state: GraphState) -> GraphState:
    """并行执行欺诈分 + 舆情分析（asyncio.gather + return_exceptions=True）。

    单项失败保守兜底（fraud=100 / sentiment=HIGH）并转人工，绝不自动放行；
    同时保留各自 usage 与耗时，供评测与观测使用。
    """
    started_at = time.perf_counter()
    if state.get("intent_route") == "strong_signal":
        # Node A 已写入确定性分数，跳过 LLM（省 Token），决策语义不变
        state.setdefault("fallback_reasons", [])
        state.setdefault("token_usage", {})["intent"] = {"skipped_llm": True}
        state.setdefault("latency_breakdown", {})["fraud_ms"] = 0.0
        state.setdefault("latency_breakdown", {})["sentiment_ms"] = 0.0
        state.setdefault("latency_breakdown", {})["risk_parallel_ms"] = 0.0
        return state
    ocr = state.get("masked_ocr_text") or state.get("ocr_text", "")
    material = f"退款金额：{state.get('amount')}\n凭证 OCR：{ocr}"
    client = _risk_client
    if hasattr(client, "score_fraud_with_usage_and_reason") and hasattr(
        client, "classify_sentiment_with_usage_and_reason"
    ):
        fraud, sentiment, fraud_usage, sentiment_usage, fraud_ms, sentiment_ms, fallback_reasons = (
            asyncio.run(score_risk_parallel_with_usage_and_fallbacks(client, material))
        )
    elif hasattr(client, "score_fraud_with_usage") and hasattr(client, "classify_sentiment_with_usage"):
        fraud, sentiment, fraud_usage, sentiment_usage, fraud_ms, sentiment_ms = asyncio.run(
            score_risk_parallel_with_usage(client, material)
        )
        fallback_reasons = []
    else:
        # 兼容旧客户端：串行兜底，usage 离线估算
        fraud = client.score_fraud(material)
        sentiment = client.classify_sentiment(material)
        fraud_usage = _legacy_usage(material, str(fraud))
        sentiment_usage = _legacy_usage(material, sentiment)
        fraud_ms = sentiment_ms = 0.0
        fallback_reasons = []
    state["fraud_score"] = int(fraud)
    state["sentiment"] = sentiment
    state["fallback_reasons"] = list(dict.fromkeys(fallback_reasons))
    state.setdefault("token_usage", {})["fraud"] = fraud_usage.as_dict()
    state.setdefault("token_usage", {})["sentiment"] = sentiment_usage.as_dict()
    state.setdefault("latency_breakdown", {})["fraud_ms"] = round(fraud_ms, 2)
    state.setdefault("latency_breakdown", {})["sentiment_ms"] = round(sentiment_ms, 2)
    state.setdefault("latency_breakdown", {})["risk_parallel_ms"] = round(
        (time.perf_counter() - started_at) * 1000, 2
    )
    return state


def route_after_risk(state: GraphState) -> str:
    """risk 之后按是否发生显式兜底分流到 fallback 节点。"""
    return "fallback" if state.get("fallback_reasons") else "decision"


def fallback_node(state: GraphState) -> GraphState:
    """显式兜底节点：把 fallback_reasons 合并进决策原因，保证异常路径可审计。"""
    reasons = list(state.get("fallback_reasons", []))
    merged = list(state.get("decision_reasons", []))
    for reason in reasons:
        if reason not in merged:
            merged.append(reason)
    state["decision_reasons"] = merged
    return state


def _legacy_usage(input_text: str, output_text: str) -> UsageSnapshot:
    input_tokens = estimate_prompt_tokens(input_text)
    output_tokens = estimate_prompt_tokens(output_text)
    return UsageSnapshot(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        measurement_type="estimated",
    )


def decision_node(state: GraphState) -> GraphState:
    started_at = time.perf_counter()
    result = decide_with_reasons(
        float(state["amount"]),
        float(state.get("ocr_confidence", 0.0)),
        int(state.get("fraud_score", 0)),
        str(state.get("sentiment", "LOW")),
        ocr_text=state.get("ocr_text", ""),
        security_risk=float(state.get("critic_risk", 0.0)),
    )
    state["decision"] = result.route
    reasons = list(result.reasons)
    for reason in state.get("fallback_reasons", []):
        if reason not in reasons:
            reasons.append(reason)
    state["decision_reasons"] = reasons
    state["evidence_audit"] = audit_evidence(
        float(state["amount"]), state.get("ocr_text")
    )
    state["evidence_audit"]["security"] = {
        "risk": state.get("critic_risk", 0.0),
        "flags": state.get("security_flags", []),
    }
    state["evidence_audit"]["intent"] = {
        "route": state.get("intent_route"),
        "label": state.get("intent_label"),
        "hit_rules": state.get("intent_hit_rules", []),
    }
    state["evidence_audit"]["fallback"] = {
        "reasons": state.get("fallback_reasons", []),
    }
    decision = result.route
    if result.route == "AUTO_REFUND":
        verdict = _action_policy.evaluate(
            ActionRequest(
                action="record_auto_refund",
                decision=result.route,
                security_risk=float(state.get("critic_risk", 0.0)),
                security_flags=tuple(state.get("security_flags", [])),
            )
        )
        state["action_policy_result"] = {
            "allowed": verdict.allowed,
            "reason": verdict.reason,
        }
        state["evidence_audit"]["action_policy"] = state["action_policy_result"]
        if verdict.allowed:
            state["final_decision"] = "AUTO_REFUNDED"
        else:
            decision = "HUMAN_REVIEW"
            state["final_decision"] = "PENDING"
            if "action_policy_denied" not in reasons:
                reasons.append("action_policy_denied")
    state["decision"] = decision
    state["decision_reasons"] = reasons
    state["management_suggestion"] = management_suggestion(decision, reasons)
    state.setdefault("latency_breakdown", {})["decision_ms"] = (
        time.perf_counter() - started_at
    ) * 1000
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
