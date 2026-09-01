"""LangGraph 决策流编排。graph.py 只负责编排，不含业务规则。"""
from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import GraphState


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("intake", nodes.intake)
    g.add_node("ocr", nodes.ocr_node)
    g.add_node("critic", nodes.critic_node)
    g.add_node("intent", nodes.intent_node)
    g.add_node("risk", nodes.risk_node)
    g.add_node("fallback", nodes.fallback_node)
    g.add_node("decision", nodes.decision_node)
    g.add_node("human_review", nodes.human_review_node)

    g.add_edge(START, "intake")
    g.add_edge("intake", "ocr")
    g.add_edge("ocr", "critic")
    g.add_edge("critic", "intent")
    g.add_conditional_edges(
        "intent",
        nodes.route_intent,
        {"strong_signal": "decision", "llm_judge": "risk"},
    )
    g.add_conditional_edges(
        "risk",
        nodes.route_after_risk,
        {"fallback": "fallback", "decision": "decision"},
    )
    g.add_edge("fallback", "decision")
    g.add_conditional_edges(
        "decision",
        nodes.route_after_decision,
        {"AUTO_REFUND": END, "HUMAN_REVIEW": "human_review"},
    )
    g.add_edge("human_review", END)
    return g
