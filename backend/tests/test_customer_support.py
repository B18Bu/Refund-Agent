from app.customer_assistant.models import CustomerSupportCase, CustomerSupportConversation, CustomerSupportMessage
from app.models import Role, User
from app.security import hash_password


def _auth_headers(client, username: str) -> dict[str, str]:
    token = client.post("/api/auth/login", json={"username": username, "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_case(db_session, customer: User, status: str, assigned_to: int | None = None) -> CustomerSupportCase:
    conversation = CustomerSupportConversation(user_id=customer.id)
    db_session.add(conversation)
    db_session.flush()
    case = CustomerSupportCase(
        conversation_id=conversation.id,
        user_id=customer.id,
        trigger_reason="USER_REQUEST",
        status=status,
        assigned_to=assigned_to,
    )
    db_session.add(case)
    db_session.commit()
    return case


def test_support_message_apis_filter_cases_require_assignment_and_hide_other_customers(client, db_session):
    customer = User(username="support-api-customer", password_hash=hash_password("secret123"), role=Role.CUSTOMER)
    other_customer = User(username="support-api-other", password_hash=hash_password("secret123"), role=Role.CUSTOMER)
    agent = User(username="support-api-agent", password_hash=hash_password("secret123"), role=Role.CS)
    db_session.add_all([customer, other_customer, agent])
    db_session.commit()
    open_case = _seed_case(db_session, customer, "OPEN")
    in_progress_case = _seed_case(db_session, customer, "IN_PROGRESS", agent.id)
    resolved_case = _seed_case(db_session, customer, "RESOLVED", agent.id)

    customer_headers = _auth_headers(client, customer.username)
    other_customer_headers = _auth_headers(client, other_customer.username)
    agent_headers = _auth_headers(client, agent.username)

    cases = client.get("/api/customer-support/cases", headers=agent_headers)
    assert cases.status_code == 200
    assert {row["id"] for row in cases.json()} == {open_case.id, in_progress_case.id}
    assert client.get(
        f"/api/customer-support/cases/{resolved_case.id}/messages",
        headers=agent_headers,
    ).status_code == 404
    assert client.post(
        f"/api/customer-support/cases/{in_progress_case.id}/messages",
        headers=agent_headers,
        json={"content": "   "},
    ).status_code == 422

    reply = client.post(
        f"/api/customer-support/cases/{in_progress_case.id}/messages",
        headers=agent_headers,
        json={"content": "请联系 13812340000"},
    )
    assert reply.status_code == 200
    assert reply.json()["sender"] == "AGENT"
    assert "13812340000" not in reply.json()["content"]

    own_messages = client.get(
        f"/api/customer-assistant/conversations/{in_progress_case.conversation_id}/messages",
        headers=customer_headers,
    )
    assert own_messages.status_code == 200
    assert own_messages.json()["status"] == "IN_PROGRESS"
    assert own_messages.json()["messages"][-1]["sender"] == "AGENT"
    forbidden_messages = client.get(
        f"/api/customer-assistant/conversations/{in_progress_case.conversation_id}/messages",
        headers=other_customer_headers,
    )
    assert forbidden_messages.status_code == 404


def test_customer_messages_return_resolved_case_status_without_leaking_other_customer_conversation(client, db_session):
    customer = User(username="resolved-status-customer", password_hash=hash_password("secret123"), role=Role.CUSTOMER)
    other_customer = User(username="resolved-status-other", password_hash=hash_password("secret123"), role=Role.CUSTOMER)
    db_session.add_all([customer, other_customer])
    db_session.commit()
    resolved_case = _seed_case(db_session, customer, "RESOLVED")
    db_session.add(CustomerSupportMessage(
        conversation_id=resolved_case.conversation_id,
        sender="AGENT",
        content_masked="问题已处理完成",
        evidence={},
    ))
    db_session.commit()

    response = client.get(
        f"/api/customer-assistant/conversations/{resolved_case.conversation_id}/messages",
        headers=_auth_headers(client, customer.username),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "RESOLVED"
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["sender"] == "AGENT"
    assert payload["messages"][0]["content"] == "问题已处理完成"
    assert client.get(
        f"/api/customer-assistant/conversations/{resolved_case.conversation_id}/messages",
        headers=_auth_headers(client, other_customer.username),
    ).status_code == 404


def test_resolved_case_rejects_customer_messages_with_conflict(client, db_session):
    customer = User(username="resolved-write-customer", password_hash=hash_password("secret123"), role=Role.CUSTOMER)
    db_session.add(customer)
    db_session.commit()
    resolved_case = _seed_case(db_session, customer, "RESOLVED")

    response = client.post(
        f"/api/customer-assistant/conversations/{resolved_case.conversation_id}/messages",
        headers=_auth_headers(client, customer.username),
        json={"message": "还有问题", "context": {}},
    )

    assert response.status_code == 409
    assert "已结束" in response.json()["detail"]


def test_new_customer_and_agent_messages_refresh_case_updated_at(db_session):
    from datetime import datetime

    from app.customer_assistant.conversations import ConversationService

    customer = User(username="case-time-customer", password_hash="unused", role=Role.CUSTOMER)
    agent = User(username="case-time-agent", password_hash="unused", role=Role.CS)
    db_session.add_all([customer, agent])
    db_session.commit()
    case = _seed_case(db_session, customer, "IN_PROGRESS", agent.id)
    original_time = datetime(2000, 1, 1)
    case.updated_at = original_time
    db_session.commit()

    service = ConversationService(db_session)
    service.reply(case.conversation_id, customer.id, "订单状态")
    db_session.refresh(case)
    assert case.updated_at > original_time

    case.updated_at = original_time
    db_session.commit()
    service.add_agent_message(case.id, agent.id, "正在为你查询")
    db_session.refresh(case)
    assert case.updated_at > original_time


def test_customer_messages_return_no_case_status_for_own_unescalated_conversation(client, db_session):
    customer = User(username="no-case-status-customer", password_hash=hash_password("secret123"), role=Role.CUSTOMER)
    db_session.add(customer)
    db_session.commit()
    conversation = CustomerSupportConversation(user_id=customer.id)
    db_session.add(conversation)
    db_session.commit()

    response = client.get(
        f"/api/customer-assistant/conversations/{conversation.id}/messages",
        headers=_auth_headers(client, customer.username),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "NO_CASE", "messages": []}
