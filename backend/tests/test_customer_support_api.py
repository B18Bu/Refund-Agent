from app.models import Role, User
from app.security import hash_password


def test_customer_support_queue_requires_customer_service_role(client, db_session):
    db_session.add(User(username="support-queue-customer", password_hash=hash_password("secret123"), role=Role.CUSTOMER))
    db_session.add(User(username="support-queue-cs", password_hash=hash_password("secret123"), role=Role.CS))
    db_session.commit()
    customer = client.post("/api/auth/login", json={"username": "support-queue-customer", "password": "secret123"}).json()["access_token"]
    cs = client.post("/api/auth/login", json={"username": "support-queue-cs", "password": "secret123"}).json()["access_token"]

    assert client.get("/api/customer-support/cases", headers={"Authorization": f"Bearer {customer}"}).status_code == 403
    assert client.get("/api/customer-support/cases", headers={"Authorization": f"Bearer {cs}"}).status_code == 200
