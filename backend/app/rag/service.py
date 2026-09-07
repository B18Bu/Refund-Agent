"""将安全的主管上下文编排为政策检索，并以不可用状态降级。"""
from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.models import Ticket, User
from app.rag.embeddings import EmbeddingClient, EmbeddingUnavailable
from app.rag.models import RagQueryLog
from app.rag.retriever import RagRetriever
from app.rag.schemas import KnowledgeResult
from app.security.gateway import DLP


class KnowledgeService:
    def __init__(self, session: Session, embedding_client: EmbeddingClient | None = None):
        self._session = session
        self._embedding_client = embedding_client or EmbeddingClient()

    def search_ticket(self, user: User, ticket: Ticket) -> KnowledgeResult:
        query = _ticket_query(ticket)
        return self._search(user, query, ticket.id)

    def search_evaluations(self, user: User) -> KnowledgeResult:
        return self._search(user, "退赔决策评测 安全规则 人工审批", None)

    def _search(self, user: User, query: str, ticket_id: int | None) -> KnowledgeResult:
        try:
            vector = self._embedding_client.embed([query])[0]
            results = RagRetriever(self._session).search(vector)
            result = KnowledgeResult.ok(results) if results else KnowledgeResult.empty()
        except (EmbeddingUnavailable, OSError, RuntimeError, ValueError, SQLAlchemyError):
            return KnowledgeResult.unavailable()
        result.query_id = self._write_audit(user.id, ticket_id, query, results)
        return result

    def _write_audit(self, user_id: int, ticket_id: int | None, query: str, results) -> int | None:
        """审计失败不能使读取接口或审批链路失败；只保留脱敏摘要哈希。"""
        try:
            masked, _ = DLP.mask(query)
            audit = RagQueryLog(
                user_id=user_id,
                ticket_id=ticket_id,
                access_scope="supervisor",
                query_summary=hashlib.sha256(masked.encode("utf-8")).hexdigest(),
                hit_document_ids=[item.document_id for item in results if item.document_id is not None],
            )
            self._session.add(audit)
            self._session.flush()
            self._session.commit()
            return audit.id
        except Exception:
            self._session.rollback()
            return None


def _ticket_query(ticket: Ticket) -> str:
    """不纳入原始 OCR、图片或用户描述，只使用可审计的决策元数据。"""
    reasons = ticket.decision_reasons if isinstance(ticket.decision_reasons, list) else []
    audit = ticket.evidence_audit if isinstance(ticket.evidence_audit, dict) else {}
    return " ".join([
        "退赔政策", f"金额 {float(ticket.amount):.2f}", f"决定 {ticket.decision.value}",
        f"风险 {ticket.fraud_score if ticket.fraud_score is not None else '未知'}",
        f"舆情 {ticket.sentiment or '未知'}", "命中原因 " + " ".join(map(str, reasons)),
        "审计 " + " ".join(sorted(map(str, audit.keys()))),
    ])
