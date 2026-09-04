"""电商核心用户路径验收：浏览 → 地址 → 加购 → 下单 → 模拟支付 → 退单。"""
from app.commerce_models import CatalogState, Product, ProductVariant, ProductStatus
from app.models import Role, User
from app.security import create_access_token


def test_commerce_happy_path(client, db_session):
    product = Product(brand="vivo", name="X100", status=ProductStatus.ACTIVE)
    db_session.add(product); db_session.flush()
    variant = ProductVariant(product_id=product.id, sku="e2e-x100", variant_name="标准版", price=128, available=True)
    user = User(username="commerce-e2e", password_hash="unused", role=Role.CUSTOMER)
    db_session.add_all([variant, user, CatalogState(id=1, status="READY")]); db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}
    assert client.get("/api/shop/products").status_code == 200
    address = {"recipient_name":"验收用户","phone":"13900000000","province":"广东","city":"深圳","district":"南山","detail":"科技园","is_default":True}
    address_id = client.post("/api/shop/addresses", json=address, headers=headers).json()["id"]
    assert client.put(f"/api/shop/cart/items/{variant.id}", json={"quantity":1}, headers=headers).status_code == 200
    order = client.post("/api/shop/orders", json={"address_id":address_id}, headers={**headers,"X-Idempotency-Key":"e2e-order"})
    assert order.status_code == 201
    paid = client.post(f"/api/shop/orders/{order.json()['id']}/simulate-pay", headers=headers)
    assert paid.json()["status"] == "PAID_SIMULATED"
    ret = client.post(f"/api/shop/orders/{order.json()['id']}/returns", json={"order_item_id":order.json()["items"][0]["id"],"reason":"质量问题"}, headers={**headers,"X-Idempotency-Key":"e2e-return"})
    assert ret.status_code == 201 and ret.json()["ticket_id"]
