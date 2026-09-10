from app.models import Role, User
from app.security import hash_password


def test_customer_lists_only_own_conversations_in_recent_activity_order(client, db_session):
    from app.customer_assistant.models import CustomerSupportCase, CustomerSupportConversation, CustomerSupportMessage

    customer = User(username="support-history-customer", password_hash=hash_password("secret123"), role=Role.CUSTOMER)
    other = User(username="support-history-other", password_hash=hash_password("secret123"), role=Role.CUSTOMER)
    db_session.add_all([customer, other]); db_session.flush()
    first = CustomerSupportConversation(user_id=customer.id)
    latest = CustomerSupportConversation(user_id=customer.id)
    foreign = CustomerSupportConversation(user_id=other.id)
    db_session.add_all([first, latest, foreign]); db_session.flush()
    db_session.add_all([
        CustomerSupportMessage(conversation_id=first.id, sender="CUSTOMER", content_masked="第一条咨询", evidence={}),
        CustomerSupportMessage(conversation_id=latest.id, sender="CUSTOMER", content_masked="最近咨询", evidence={}),
        CustomerSupportMessage(conversation_id=foreign.id, sender="CUSTOMER", content_masked="他人咨询", evidence={}),
        CustomerSupportCase(conversation_id=latest.id, user_id=customer.id, trigger_reason="USER_REQUEST", status="RESOLVED"),
    ])
    db_session.commit()
    token = client.post("/api/auth/login", json={"username": customer.username, "password": "secret123"}).json()["access_token"]

    response = client.get("/api/customer-assistant/conversations", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": latest.id, "status": "RESOLVED", "summary_masked": "最近咨询"},
        {"id": first.id, "status": "NO_CASE", "summary_masked": "第一条咨询"},
    ]


def test_customer_support_queue_requires_customer_service_role(client, db_session):
    db_session.add(User(username="support-queue-customer", password_hash=hash_password("secret123"), role=Role.CUSTOMER))
    db_session.add(User(username="support-queue-cs", password_hash=hash_password("secret123"), role=Role.CS))
    db_session.commit()
    customer = client.post("/api/auth/login", json={"username": "support-queue-customer", "password": "secret123"}).json()["access_token"]
    cs = client.post("/api/auth/login", json={"username": "support-queue-cs", "password": "secret123"}).json()["access_token"]

    assert client.get("/api/customer-support/cases", headers={"Authorization": f"Bearer {customer}"}).status_code == 403
    assert client.get("/api/customer-support/cases", headers={"Authorization": f"Bearer {cs}"}).status_code == 200
