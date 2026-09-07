from app.models import Decision, Role, Ticket, TicketStatus, User
from app.rag.schemas import KnowledgeEvidence, KnowledgeResult
from app.security import hash_password


def _login(client, db_session, username: str, role: Role) -> tuple[str, User]:
    user = User(username=username, password_hash=hash_password("secret123"), role=role)
    db_session.add(user)
    db_session.commit()
    token = client.post("/api/auth/login", json={"username": username, "password": "secret123"}).json()["access_token"]
    return token, user


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _ticket(db_session, user_id: int) -> Ticket:
    ticket = Ticket(ticket_no="rag-api-ticket", user_id=user_id, amount=128, image_paths=[], status=TicketStatus.RUNNING, decision=Decision.PENDING)
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def test_customer_service_cannot_read_knowledge(client, db_session):
    token, user = _login(client, db_session, "rag-cs", Role.CS)
    ticket = _ticket(db_session, user.id)

    assert client.get(f"/api/tickets/{ticket.id}/knowledge", headers=_auth(token)).status_code == 403
    assert client.get("/api/evaluations/knowledge", headers=_auth(token)).status_code == 403


def test_supervisor_gets_traceable_ticket_knowledge(client, db_session, monkeypatch):
    from app.rag.models import RagQueryLog

    token, user = _login(client, db_session, "rag-sv", Role.SV)
    ticket = _ticket(db_session, user.id)

    monkeypatch.setattr("app.rag.service.EmbeddingClient.embed", lambda *_args: [[1.0] + [0.0] * 511])
    monkeypatch.setattr("app.rag.service.RagRetriever.search", lambda *_args: [
        KnowledgeEvidence(
            content="128 元仅在低风险条件下自动决策",
            source="docs/guides/refund.md",
            section="自动退赔",
            version="v1",
            similarity=0.91,
            document_id=7,
        )
    ])

    response = client.get(f"/api/tickets/{ticket.id}/knowledge", headers=_auth(token))

    assert response.status_code == 200
    assert response.json() == {
        "available": True, "query_id": response.json()["query_id"], "status": "ok",
        "results": [{"content": "128 元仅在低风险条件下自动决策", "source": "docs/guides/refund.md", "section": "自动退赔", "version": "v1", "similarity": 0.91}],
    }
    audit = db_session.get(RagQueryLog, response.json()["query_id"])
    assert audit is not None
    assert audit.ticket_id == ticket.id


def test_embedding_failure_returns_unavailable_without_decision_change(client, db_session, monkeypatch):
    from app.routers import knowledge

    token, user = _login(client, db_session, "rag-unavailable-sv", Role.SV)
    ticket = _ticket(db_session, user.id)
    monkeypatch.setattr(knowledge.KnowledgeService, "search_ticket", lambda *_args: KnowledgeResult.unavailable())

    response = client.get(f"/api/tickets/{ticket.id}/knowledge", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["status"] == "unavailable"
    db_session.refresh(ticket)
    assert ticket.decision == Decision.PENDING


def test_evaluation_knowledge_query_is_supervisor_only_and_uses_safe_status(client, db_session, monkeypatch):
    from app.routers import knowledge

    token, _ = _login(client, db_session, "rag-evaluation-sv", Role.SV)
    monkeypatch.setattr(knowledge.KnowledgeService, "search_evaluations", lambda *_args: KnowledgeResult.empty())

    response = client.get("/api/evaluations/knowledge", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["status"] == "empty"
    assert response.json()["results"] == []


def test_search_audit_uses_masked_hash_and_hit_document_ids(db_session, monkeypatch):
    from app.rag.models import RagQueryLog
    from app.rag.service import KnowledgeService

    user = User(username="rag-audit-sv", password_hash="hash", role=Role.SV)
    db_session.add(user)
    db_session.commit()

    class Embeddings:
        def embed(self, _texts):
            return [[1.0] + [0.0] * 511]

    monkeypatch.setattr("app.rag.service.RagRetriever.search", lambda *_args: [
        KnowledgeEvidence(content="规则", source="docs/guides/refund.md", section="退款", version="v1", similarity=0.9, document_id=7)
    ])

    result = KnowledgeService(db_session, Embeddings()).search_evaluations(user)

    assert result.status == "ok"
    audit = db_session.query(RagQueryLog).one()
    assert result.query_id == audit.id
    assert audit.query_summary != "退赔决策评测 安全规则 人工审批"
    assert audit.hit_document_ids == [7]


def test_database_failure_returns_unavailable(db_session, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app.rag.service import KnowledgeService

    user = User(username="rag-db-unavailable-sv", password_hash="hash", role=Role.SV)
    db_session.add(user)
    db_session.commit()

    class Embeddings:
        def embed(self, _texts):
            return [[1.0] + [0.0] * 511]

    def fail_search(*_args):
        raise OperationalError("SELECT", {}, RuntimeError("数据库不可用"))

    monkeypatch.setattr("app.rag.service.RagRetriever.search", fail_search)

    result = KnowledgeService(db_session, Embeddings()).search_evaluations(user)

    assert result.status == "unavailable"
