from app.models import Role, User
from app.security import hash_password
from datetime import datetime


def _token(client, db_session, username: str, role: Role) -> str:
    db_session.add(User(username=username, password_hash=hash_password("secret123"), role=role))
    db_session.commit()
    return client.post("/api/auth/login", json={"username": username, "password": "secret123"}).json()["access_token"]


def test_customer_assistant_only_allows_customer_role(client, db_session):
    token = _token(client, db_session, "assistant-cs", Role.CS)

    response = client.post(
        "/api/customer-assistant/reply",
        json={"message": "推荐手机", "context": {}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_customer_assistant_requires_jwt(client):
    response = client.post("/api/customer-assistant/reply", json={"message": "推荐手机", "context": {}})

    assert response.status_code == 401


def test_customer_assistant_rejects_unknown_context_fields(client, db_session):
    token = _token(client, db_session, "assistant-context-contract", Role.CUSTOMER)

    response = client.post(
        "/api/customer-assistant/reply",
        json={"message": "推荐手机", "context": {"unexpected_scope": "ignore this"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_customer_assistant_reply_returns_source_crawl_time(client, db_session):
    from app.commerce_models import Product, ProductStatus
    from app.customer_assistant.models import CustomerCatalogChunk

    token = _token(client, db_session, "assistant-source-contract", Role.CUSTOMER)
    product = Product(brand="vivo", name="X100", status=ProductStatus.ACTIVE)
    db_session.add(product)
    db_session.flush()
    db_session.add(CustomerCatalogChunk(
        product_id=product.id,
        source_url="https://example.test/x100",
        source_hash="source-contract",
        content="vivo X100 手机，适合拍照",
        content_hash="content-contract",
        crawled_at=datetime(2026, 9, 7, 8, 30),
        embedding=[0.0] * 512,
    ))
    db_session.commit()

    response = client.post(
        "/api/customer-assistant/reply",
        json={"message": "推荐拍照手机", "context": {}},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["sources"] == [{
        "source_url": "https://example.test/x100",
        "crawled_at": "2026-09-07T08:30:00",
    }]
