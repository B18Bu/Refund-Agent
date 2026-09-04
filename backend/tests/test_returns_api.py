from app.commerce_models import Order, OrderItem, OrderStatus, Product, ProductVariant, ReturnRequest
from app.models import Decision, Role, Ticket, TicketStatus, User
from app.security import create_access_token


def _headers(db_session, username="return-api-user"):
    user = User(username=username, password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}, user


def _paid_order(db_session, user):
    product = Product(brand="vivo", name="X100", status="ACTIVE")
    db_session.add(product)
    db_session.flush()
    variant = ProductVariant(product_id=product.id, sku=f"sku-{user.id}", variant_name="标准版", price=100, spec_json={})
    db_session.add(variant)
    db_session.flush()
    order = Order(order_no=f"O-{user.id}", user_id=user.id, status=OrderStatus.PAID_SIMULATED,
                  address_snapshot_json={}, total_amount=100)
    db_session.add(order)
    db_session.flush()
    item = OrderItem(order_id=order.id, product_id=product.id, variant_id=variant.id,
                     product_snapshot_json={"name": product.name}, quantity=1, unit_price=100)
    db_session.add(item)
    db_session.commit()
    return order, item


def _upload_return_evidence(client, headers):
    image = b"\x89PNG\r\n\x1a\n" + b"test-pixel"
    response = client.post(
        "/api/shop/return-evidence",
        files=[("files", ("proof.png", image, "image/png"))],
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["storage_keys"]


def test_return_requires_paid_order_and_idempotency(client, db_session):
    headers, user = _headers(db_session)
    order, item = _paid_order(db_session, user)
    missing = client.post(f"/api/shop/orders/{order.id}/returns", json={"order_item_id": item.id, "reason": "质量问题"}, headers=headers)
    assert missing.status_code == 400
    db_session.query(Order).filter(Order.id == order.id).update({Order.status: OrderStatus.CREATED})
    db_session.commit()
    blocked = client.post(f"/api/shop/orders/{order.id}/returns", json={"order_item_id": item.id, "reason": "质量问题"}, headers={**headers, "X-Idempotency-Key": "r-1"})
    assert blocked.status_code == 409


def test_return_validation_failure_does_not_poison_idempotency_key(client, db_session):
    headers, user = _headers(db_session, "return-retry")
    order, item = _paid_order(db_session, user)
    db_session.query(Order).filter(Order.id == order.id).update({Order.status: OrderStatus.CREATED})
    db_session.commit()

    first = client.post(
        f"/api/shop/orders/{order.id}/returns",
        json={"order_item_id": item.id, "reason": "质量问题"},
        headers={**headers, "X-Idempotency-Key": "retry-key"},
    )
    assert first.status_code == 409

    db_session.query(Order).filter(Order.id == order.id).update({Order.status: OrderStatus.PAID_SIMULATED})
    db_session.commit()
    retry = client.post(
        f"/api/shop/orders/{order.id}/returns",
        json={"order_item_id": item.id, "reason": "质量问题"},
        headers={**headers, "X-Idempotency-Key": "retry-key"},
    )
    assert retry.status_code == 201


def test_return_creates_one_ticket_and_is_idempotent(client, db_session):
    headers, user = _headers(db_session, "return-idem")
    order, item = _paid_order(db_session, user)
    payload = {"order_item_id": item.id, "reason": "质量问题", "description": "屏幕异常", "evidence_paths": _upload_return_evidence(client, headers)}
    first = client.post(f"/api/shop/orders/{order.id}/returns", json=payload, headers={**headers, "X-Idempotency-Key": "same"})
    assert first.status_code == 201
    second = client.post(f"/api/shop/orders/{order.id}/returns", json=payload, headers={**headers, "X-Idempotency-Key": "same"})
    assert second.status_code == 201 and second.json()["id"] == first.json()["id"]
    assert db_session.query(ReturnRequest).count() == 1
    ticket = db_session.query(Ticket).one()
    assert ticket.image_paths == payload["evidence_paths"]
    assert ticket.description == "屏幕异常"


def test_return_without_evidence_is_forced_to_manual_review(client, db_session):
    headers, user = _headers(db_session, "return-missing-evidence")
    order, item = _paid_order(db_session, user)

    response = client.post(
        f"/api/shop/orders/{order.id}/returns",
        json={"order_item_id": item.id, "reason": "商品质量问题"},
        headers={**headers, "X-Idempotency-Key": "missing-evidence"},
    )

    assert response.status_code == 201
    ticket = db_session.query(Ticket).one()
    assert ticket.status == TicketStatus.SUSPENDED
    assert ticket.decision == Decision.PENDING
    assert ticket.decision_reasons == ["MISSING_RETURN_EVIDENCE"]


def test_return_rejects_uncontrolled_local_filename_as_evidence(client, db_session):
    headers, user = _headers(db_session, "return-uncontrolled-evidence")
    order, item = _paid_order(db_session, user)

    response = client.post(
        f"/api/shop/orders/{order.id}/returns",
        json={"order_item_id": item.id, "reason": "商品质量问题", "evidence_paths": ["photo.jpg"]},
        headers={**headers, "X-Idempotency-Key": "uncontrolled-evidence"},
    )

    assert response.status_code == 422


def test_customer_can_upload_return_evidence_before_creating_return(client, db_session):
    headers, _user = _headers(db_session, "return-upload")
    storage_keys = _upload_return_evidence(client, headers)
    assert storage_keys[0].startswith("uploads/")


def test_return_status_mapping_is_deterministic():
    from app.commerce_service import map_ticket_to_return_status
    assert map_ticket_to_return_status("RUNNING", "PENDING").value == "PROCESSING"
    assert map_ticket_to_return_status("SUSPENDED", "PENDING").value == "PENDING_REVIEW"
    assert map_ticket_to_return_status("COMPLETED", "AUTO_REFUNDED").value == "APPROVED"
    assert map_ticket_to_return_status("COMPLETED", "APPROVED").value == "APPROVED"
    assert map_ticket_to_return_status("COMPLETED", "REJECTED").value == "REJECTED"
    assert map_ticket_to_return_status("COMPLETED", "FAILED").value == "FAILED"


def test_returns_list_and_detail(client, db_session):
    headers, user = _headers(db_session, "return-list")
    order, item = _paid_order(db_session, user)
    response = client.post(f"/api/shop/orders/{order.id}/returns", json={"order_item_id": item.id, "reason": "不喜欢"}, headers={**headers, "X-Idempotency-Key": "list-1"})
    assert response.status_code == 201
    assert client.get("/api/shop/returns", headers=headers).status_code == 200
    assert client.get(f"/api/shop/returns/{response.json()['id']}", headers=headers).status_code == 200


def test_return_idempotency_key_is_scoped_to_user(client, db_session):
    first_headers, first_user = _headers(db_session, "return-key-user-one")
    second_headers, second_user = _headers(db_session, "return-key-user-two")
    first_order, first_item = _paid_order(db_session, first_user)
    second_order, second_item = _paid_order(db_session, second_user)
    first = client.post(f"/api/shop/orders/{first_order.id}/returns", json={"order_item_id": first_item.id, "reason": "质量问题"}, headers={**first_headers, "X-Idempotency-Key": "shared-key"})
    second = client.post(f"/api/shop/orders/{second_order.id}/returns", json={"order_item_id": second_item.id, "reason": "质量问题"}, headers={**second_headers, "X-Idempotency-Key": "shared-key"})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_return_queue_failure_is_503_then_idempotently_reports_failed(client, db_session, redis_client):
    from app.main import app
    from app.redis_client import get_redis

    class QueueFailureRedis:
        def set(self, *args, **kwargs):
            return redis_client.set(*args, **kwargs)

        def get(self, *args, **kwargs):
            return redis_client.get(*args, **kwargs)

        def xadd(self, *args, **kwargs):
            raise RuntimeError("redis unavailable")

    headers, user = _headers(db_session, "return-queue-failure")
    order, item = _paid_order(db_session, user)
    app.dependency_overrides[get_redis] = lambda: QueueFailureRedis()
    try:
        first = client.post(f"/api/shop/orders/{order.id}/returns", json={"order_item_id": item.id, "reason": "质量问题", "evidence_paths": _upload_return_evidence(client, headers)}, headers={**headers, "X-Idempotency-Key": "queue-failure-key"})
        assert first.status_code == 503
        replay = client.post(f"/api/shop/orders/{order.id}/returns", json={"order_item_id": item.id, "reason": "质量问题", "evidence_paths": _upload_return_evidence(client, headers)}, headers={**headers, "X-Idempotency-Key": "queue-failure-key"})
        assert replay.status_code == 200
        assert replay.json()["status"] == "FAILED"
        assert db_session.query(ReturnRequest).count() == 1
        assert db_session.query(Ticket).count() == 1
    finally:
        app.dependency_overrides.pop(get_redis, None)
