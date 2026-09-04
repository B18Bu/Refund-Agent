"""商品目录游客只读接口。"""
from app.commerce_models import Order, OrderStatus, Product, ProductStatus, ProductVariant
from app.models import Role, User
from app.security import create_access_token


def _seed_products(db_session):
    vivo = Product(brand="vivo", name="X100 Pro", model="X100", status=ProductStatus.ACTIVE,
                   source_url="https://www.vivo.com.cn/products/x100")
    oppo = Product(brand="OPPO", name="Find X8", status=ProductStatus.ACTIVE,
                   source_url="https://www.oppo.com/cn/find-x8")
    db_session.add_all([vivo, oppo])
    db_session.flush()
    db_session.add_all([
        ProductVariant(product_id=vivo.id, sku="vivo-x100", variant_name="标准版", spec_json={}, price=3999),
        ProductVariant(product_id=oppo.id, sku="oppo-find-x8", variant_name="标准版", spec_json={}, price=4299),
    ])
    db_session.commit()


def test_guest_product_list_filters_and_paginates(client, db_session):
    _seed_products(db_session)
    response = client.get("/api/shop/products", params={"brand": "vivo", "keyword": "X100", "max_price": 4000, "page_size": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["brand"] == "vivo"


def test_product_detail_404_and_brands(client, db_session):
    _seed_products(db_session)
    assert client.get("/api/shop/products/99999").status_code == 404
    response = client.get("/api/shop/brands")
    assert response.status_code == 200
    assert response.json() == ["OPPO", "vivo"]


def _user_headers(db_session, username="buyer"):
    user = User(username=username, password_hash="unused", role=Role.CS)
    db_session.add(user)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}, user


def _seed_buyable(db_session):
    product = Product(brand="vivo", name="X100", status=ProductStatus.ACTIVE)
    db_session.add(product)
    db_session.flush()
    variant = ProductVariant(product_id=product.id, sku="shop-x100", variant_name="标准版", spec_json={"ram": "12GB"}, price=3999, available=True)
    db_session.add(variant)
    db_session.commit()
    return product, variant


def test_guest_shop_private_resources_require_auth(client):
    assert client.get("/api/shop/addresses").status_code == 401
    assert client.get("/api/shop/cart").status_code == 401
    assert client.get("/api/shop/orders").status_code == 401


def test_address_is_isolated_and_default_is_unique(client, db_session):
    headers, user = _user_headers(db_session, "address-owner")
    other_headers, _ = _user_headers(db_session, "address-other")
    payload = {"recipient_name": "张三", "phone": "13800000000", "province": "广东", "city": "深圳", "district": "南山", "detail": "科技园", "is_default": True}
    created = client.post("/api/shop/addresses", json=payload, headers=headers)
    assert created.status_code == 201
    address_id = created.json()["id"]
    assert client.get(f"/api/shop/addresses/{address_id}", headers=other_headers).status_code == 404
    payload["detail"] = "后海"
    second = client.post("/api/shop/addresses", json=payload, headers=headers)
    assert second.status_code == 201
    rows = client.get("/api/shop/addresses", headers=headers).json()
    assert sum(1 for row in rows if row["is_default"]) == 1


def test_address_update_delete_are_isolated(client, db_session):
    headers, _ = _user_headers(db_session, "address-edit-owner")
    other_headers, _ = _user_headers(db_session, "address-edit-other")
    payload = {"recipient_name": "张三", "phone": "13800000000", "province": "广东", "city": "深圳", "district": "南山", "detail": "科技园", "is_default": True}
    address_id = client.post("/api/shop/addresses", json=payload, headers=headers).json()["id"]
    assert client.put(f"/api/shop/addresses/{address_id}", json=payload, headers=other_headers).status_code == 404
    assert client.delete(f"/api/shop/addresses/{address_id}", headers=other_headers).status_code == 404
    payload["detail"] = "后海"
    assert client.put(f"/api/shop/addresses/{address_id}", json=payload, headers=headers).status_code == 200
    assert client.delete(f"/api/shop/addresses/{address_id}", headers=headers).status_code == 204


def test_cart_rejects_unavailable_variant_and_upserts_quantity(client, db_session):
    headers, _ = _user_headers(db_session, "cart-owner")
    _, variant = _seed_buyable(db_session)
    first = client.put(f"/api/shop/cart/items/{variant.id}", json={"quantity": 2}, headers=headers)
    assert first.status_code == 200
    second = client.put(f"/api/shop/cart/items/{variant.id}", json={"quantity": 3}, headers=headers)
    assert second.status_code == 200
    assert second.json()["quantity"] == 3
    variant.available = False
    db_session.commit()
    assert client.put(f"/api/shop/cart/items/{variant.id}", json={"quantity": 1}, headers=headers).status_code == 409


def test_order_uses_server_price_snapshot_and_idempotency(client, db_session):
    headers, user = _user_headers(db_session, "order-owner")
    product, variant = _seed_buyable(db_session)
    address = {"recipient_name": "李四", "phone": "13900000000", "province": "广东", "city": "深圳", "district": "福田", "detail": "中心城", "is_default": True}
    address_id = client.post("/api/shop/addresses", json=address, headers=headers).json()["id"]
    client.put(f"/api/shop/cart/items/{variant.id}", json={"quantity": 2, "unit_price": 1}, headers=headers)
    order = client.post("/api/shop/orders", json={"address_id": address_id}, headers={**headers, "X-Idempotency-Key": "order-key-1"})
    assert order.status_code == 201
    body = order.json()
    assert body["total_amount"] == 7998.0
    assert body["items"][0]["product_snapshot_json"]["name"] == product.name
    replay = client.post("/api/shop/orders", json={"address_id": address_id}, headers={**headers, "X-Idempotency-Key": "order-key-1"})
    assert replay.status_code == 201
    assert replay.json()["id"] == body["id"]


def test_order_requires_idempotency_and_isolated_between_users(client, db_session):
    headers1, _ = _user_headers(db_session, "order-user-one")
    headers2, _ = _user_headers(db_session, "order-user-two")
    _, variant = _seed_buyable(db_session)
    address = {"recipient_name": "李四", "phone": "13900000000", "province": "广东", "city": "深圳", "district": "福田", "detail": "中心城", "is_default": True}
    address1 = client.post("/api/shop/addresses", json=address, headers=headers1).json()["id"]
    address2 = client.post("/api/shop/addresses", json=address, headers=headers2).json()["id"]
    client.put(f"/api/shop/cart/items/{variant.id}", json={"quantity": 1}, headers=headers1)
    client.put(f"/api/shop/cart/items/{variant.id}", json={"quantity": 1}, headers=headers2)
    assert client.post("/api/shop/orders", json={"address_id": address1}, headers=headers1).status_code == 400
    first = client.post("/api/shop/orders", json={"address_id": address1}, headers={**headers1, "X-Idempotency-Key": "shared-key"})
    second = client.post("/api/shop/orders", json={"address_id": address2}, headers={**headers2, "X-Idempotency-Key": "shared-key"})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert client.get(f"/api/shop/orders/{first.json()['id']}", headers=headers2).status_code == 404
    assert client.get("/api/shop/orders", headers=headers2).json()[0]["id"] == second.json()["id"]


def _create_order_for_payment(client, db_session, username="payment-owner"):
    headers, _ = _user_headers(db_session, username)
    _, variant = _seed_buyable(db_session)
    address = {"recipient_name": "支付用户", "phone": "13900000000", "province": "广东", "city": "深圳", "district": "福田", "detail": "中心城", "is_default": True}
    address_id = client.post("/api/shop/addresses", json=address, headers=headers).json()["id"]
    client.put(f"/api/shop/cart/items/{variant.id}", json={"quantity": 1}, headers=headers)
    order = client.post("/api/shop/orders", json={"address_id": address_id}, headers={**headers, "X-Idempotency-Key": f"{username}-order"})
    assert order.status_code == 201
    return headers, order.json()


def test_simulate_payment_transitions_created_and_is_idempotent(client, db_session):
    headers, order = _create_order_for_payment(client, db_session)
    payment = client.post(f"/api/shop/orders/{order['id']}/simulate-pay", headers=headers)
    assert payment.status_code == 200
    assert payment.json()["status"] == "PAID_SIMULATED"

    replay = client.post(f"/api/shop/orders/{order['id']}/simulate-pay", headers=headers)
    assert replay.status_code == 200
    assert replay.json()["id"] == order["id"]
    assert replay.json()["status"] == "PAID_SIMULATED"


def test_simulate_payment_rejects_other_terminal_states_and_payment_secrets(client, db_session):
    headers, order = _create_order_for_payment(client, db_session, "payment-terminal")
    # A simulated payment endpoint must not accept card numbers or payment passwords.
    rejected = client.post(f"/api/shop/orders/{order['id']}/simulate-pay", json={"card_number": "4111111111111111"}, headers=headers)
    assert rejected.status_code == 422

    paid = client.post(f"/api/shop/orders/{order['id']}/simulate-pay", headers=headers)
    assert paid.status_code == 200
    db_session.query(Order).filter(Order.id == order["id"]).update({Order.status: OrderStatus.CLOSED})
    db_session.commit()
    closed = client.post(f"/api/shop/orders/{order['id']}/simulate-pay", headers=headers)
    assert closed.status_code == 409


def test_simulate_payment_and_order_queries_are_user_isolated(client, db_session):
    owner_headers, order = _create_order_for_payment(client, db_session, "payment-owner-isolated")
    other_headers, _ = _user_headers(db_session, "payment-other-isolated")
    assert client.post(f"/api/shop/orders/{order['id']}/simulate-pay", headers=other_headers).status_code == 404
    assert client.get(f"/api/shop/orders/{order['id']}", headers=other_headers).status_code == 404
    assert client.get("/api/shop/orders", headers=other_headers).json() == []
    assert client.get(f"/api/shop/orders/{order['id']}", headers=owner_headers).status_code == 200
