from app.commerce_models import Product, ProductStatus, ProductVariant
from app.models import Role, User
from app.security import create_access_token


def _customer_headers(db_session):
    user = User(username="catalog-e2e-customer", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}


def test_catalog_not_ready_rejects_browse_and_customer_cart(client, db_session):
    product = Product(brand="vivo", name="未发布商品", status=ProductStatus.ACTIVE)
    db_session.add(product)
    db_session.flush()
    variant = ProductVariant(product_id=product.id, sku="catalog-gate", variant_name="标准版", price=128, spec_json={})
    db_session.add(variant)
    db_session.commit()

    headers = _customer_headers(db_session)

    assert client.get("/api/shop/products").status_code == 503
    assert client.put(f"/api/shop/cart/items/{variant.id}", json={"quantity": 1}, headers=headers).status_code == 503
