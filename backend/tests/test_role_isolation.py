from app.models import Role, User
from app.security import create_access_token


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

