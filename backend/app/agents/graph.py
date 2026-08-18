"""LangGraph 决策流编排。graph.py 只负责编排，不含业务规则。"""
from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import GraphState


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("intake", nodes.intake)
    g.add_node("ocr", nodes.ocr_node)
    g.add_node("fraud", nodes.fraud_node)
    g.add_node("sentiment", nodes.sentiment_node)
    g.add_node("decision", nodes.decision_node)
    g.add_node("human_review", nodes.human_review_node)

    g.add_edge(START, "intake")
    g.add_edge("intake", "ocr")
    g.add_edge("ocr", "fraud")
    g.add_edge("fraud", "sentiment")
    g.add_edge("sentiment", "decision")
    g.add_conditional_edges(
        "decision",
        nodes.route_after_decision,
        {"AUTO_REFUND": END, "HUMAN_REVIEW": "human_review"},
    )
    g.add_edge("human_review", END)
    return g
