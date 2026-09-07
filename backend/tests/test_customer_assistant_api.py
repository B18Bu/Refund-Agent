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


def test_customer_privacy_api_uses_authenticated_customer_and_preserves_ignored_keys(client, db_session):
    from app.customer_assistant.models import CustomerPreferenceAudit

    token = _token(client, db_session, "privacy-api-customer", Role.CUSTOMER)
    headers = {"Authorization": f"Bearer {token}"}

    initial = client.get("/api/customer-assistant/privacy", headers=headers)
    assert initial.status_code == 200
    assert initial.json() == {"enabled": False, "preferences": [], "ignored_keys": []}

    enabled = client.put("/api/customer-assistant/privacy", json={"enabled": True}, headers=headers)
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    updated = client.put("/api/customer-assistant/privacy/preferences/brand", json={"value": ["vivo"]}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["preferences"] == [{"key": "brand", "value": ["vivo"], "manual": True}]

    deleted = client.delete("/api/customer-assistant/privacy/preferences/brand", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["preferences"] == []
    assert deleted.json()["ignored_keys"] == ["brand"]

    restored = client.delete("/api/customer-assistant/privacy/ignored/brand", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["ignored_keys"] == []

    disabled = client.put("/api/customer-assistant/privacy", json={"enabled": False}, headers=headers)
    assert disabled.status_code == 200
    assert disabled.json() == {"enabled": False, "preferences": [], "ignored_keys": []}
    assert [row.action for row in db_session.query(CustomerPreferenceAudit).order_by(CustomerPreferenceAudit.id)] == [
        "PRIVACY_ENABLED", "MANUAL_SET", "PREFERENCE_DELETED", "PREFERENCE_RESTORED", "PRIVACY_DISABLED",
    ]


def test_customer_privacy_api_forbids_user_id_and_non_customer_access(client, db_session):
    token = _token(client, db_session, "privacy-api-cs", Role.CS)
    customer_token = _token(client, db_session, "privacy-api-customer-contract", Role.CUSTOMER)

    assert client.get("/api/customer-assistant/privacy").status_code == 401
    assert client.get("/api/customer-assistant/privacy", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    response = client.put(
        "/api/customer-assistant/privacy",
        json={"enabled": True, "user_id": 999},
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert response.status_code == 422
