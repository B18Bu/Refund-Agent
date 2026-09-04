from app.commerce_models import Order, OrderItem, OrderStatus, Product, ProductVariant, ReturnRequest
from app.models import Decision, Role, Ticket, TicketStatus, User
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


def _manual_return(db_session, username="return-customer"):
    customer = User(username=username, password_hash="unused", role=Role.CUSTOMER)
    db_session.add(customer)
    db_session.flush()
    product = Product(brand="vivo", name="X100", status="ACTIVE")
    db_session.add(product)
    db_session.flush()
    variant = ProductVariant(product_id=product.id, sku=f"sku-{customer.id}", variant_name="标准版", price=128, spec_json={})
    db_session.add(variant)
    db_session.flush()
    order = Order(order_no=f"O-{customer.id}", user_id=customer.id, status=OrderStatus.RETURNING, address_snapshot_json={}, total_amount=128)
    db_session.add(order)
    db_session.flush()
    item = OrderItem(order_id=order.id, product_id=product.id, variant_id=variant.id, product_snapshot_json={"name": "X100"}, quantity=1, unit_price=128, status="RETURN_REQUESTED")
    ticket = Ticket(ticket_no=f"T-{customer.id}", user_id=customer.id, amount=128, image_paths=["uploads/proof.png"], status=TicketStatus.SUSPENDED, decision=Decision.PENDING, thread_id=f"thread-{customer.id}")
    db_session.add_all([item, ticket])
    db_session.flush()
    row = ReturnRequest(return_no=f"R-{customer.id}", order_id=order.id, order_item_id=item.id, user_id=customer.id, reason="质量问题", evidence_paths=["uploads/proof.png"], ticket_id=ticket.id, status="PENDING_REVIEW", idempotency_key=f"return-{customer.id}")
    db_session.add(row)
    db_session.commit()
    return ticket, row


def test_cs_and_sv_can_view_only_suspended_return_queue(client, db_session):
    _ticket, row = _manual_return(db_session)
    for role in (Role.CS, Role.SV):
        response = client.get("/api/tickets/service/returns", headers=_headers(db_session, f"queue-{role.value}", role))
        assert response.status_code == 200
        assert response.json()[0]["return_no"] == row.return_no
        assert response.json()[0]["evidence_paths"] == ["uploads/proof.png"]
    assert client.get("/api/tickets/service/returns", headers=_headers(db_session, "queue-customer", Role.CUSTOMER)).status_code == 403


def test_cs_and_sv_cannot_both_approve_same_return(client, db_session):
    ticket, _row = _manual_return(db_session, "approval-customer")
    cs_headers = _headers(db_session, "approval-cs", Role.CS)
    sv_headers = _headers(db_session, "approval-sv", Role.SV)

    first = client.post(f"/api/tickets/{ticket.id}/approve", json={"action": "APPROVE", "comment": "已核验"}, headers=cs_headers)
    second = client.post(f"/api/tickets/{ticket.id}/approve", json={"action": "APPROVE", "comment": "重复审批"}, headers=sv_headers)

    assert first.status_code == 200
    assert second.status_code == 409
