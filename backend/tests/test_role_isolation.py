from app.models import Role, User
from app.security import create_access_token
from app.security import hash_password


def _headers(db_session, username: str, role: Role):
    user = User(username=username, password_hash="unused", role=role)
    db_session.add(user)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


def test_customer_role_can_login_and_customer_write_endpoint_is_allowed(client, db_session):
    headers = _headers(db_session, "customer-role", Role.CUSTOMER)
    response = client.post(
        "/api/shop/addresses",
        json={"recipient_name": "用户", "phone": "13800000000", "province": "广东", "city": "深圳",
              "district": "南山", "detail": "科技园", "is_default": True},
        headers=headers,
    )
    assert response.status_code == 201


def test_customer_service_and_supervisor_cannot_write_shop_addresses(client, db_session):
    payload = {"recipient_name": "客服", "phone": "13800000000", "province": "广东", "city": "深圳",
               "district": "南山", "detail": "科技园", "is_default": True}
    for role in (Role.CS, Role.SV):
        response = client.post("/api/shop/addresses", json=payload,
                               headers=_headers(db_session, f"shop-{role.value}", role))
        assert response.status_code == 403


def test_customer_01_secret123_login(client, db_session):
    db_session.add(User(username="customer_01", password_hash=hash_password("secret123"), role=Role.CUSTOMER))
    db_session.commit()
    response = client.post("/api/auth/login", json={"username": "customer_01", "password": "secret123"})
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_staff_cannot_read_or_write_customer_shop_resources(client, db_session):
    for role in (Role.CS, Role.SV):
        headers = _headers(db_session, f"staff-shop-{role.value}", role)
        assert client.get("/api/shop/cart", headers=headers).status_code == 403
        assert client.get("/api/shop/orders", headers=headers).status_code == 403
        assert client.get("/api/shop/returns", headers=headers).status_code == 403
        assert client.put("/api/shop/cart/items/1", json={"quantity": 1}, headers=headers).status_code == 403
        assert client.post("/api/shop/orders", json={"address_id": 1}, headers={**headers, "X-Idempotency-Key": "staff-order"}).status_code == 403
        assert client.post("/api/shop/orders/1/returns", json={"order_item_id": 1, "reason": "test"}, headers={**headers, "X-Idempotency-Key": "staff-return"}).status_code == 403


def test_role_migration_adds_customer_enum_value():
    from pathlib import Path
    migration = Path(__file__).parents[1] / "migrations" / "20260904_add_customer_role.sql"
    sql = migration.read_text(encoding="utf-8").lower()
    assert "alter type role add value if not exists 'customer'" in sql
