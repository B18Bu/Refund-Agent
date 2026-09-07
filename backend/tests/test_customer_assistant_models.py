"""消费者偏好可用订单和完成订单接口的回归测试。"""

from datetime import datetime, timedelta

from app.commerce_models import (Order, OrderItem, OrderItemStatus, OrderStatus,
                                 Product, ProductStatus, ProductVariant)
from app.models import Role, User
from app.security import create_access_token


def _order_with_item(db_session, user, order_no, status, created_at, item_status=OrderItemStatus.NORMAL):
    product = Product(brand="vivo", name=f"X{order_no}", status=ProductStatus.ACTIVE)
    db_session.add(product)
    db_session.flush()
    variant = ProductVariant(product_id=product.id, sku=f"sku-{order_no}", variant_name="标准版", spec_json={}, price=100)
    order = Order(order_no=order_no, user_id=user.id, address_snapshot_json={}, status=status,
                  total_amount=100, created_at=created_at)
    db_session.add_all([variant, order])
    db_session.flush()
    item = OrderItem(order_id=order.id, product_id=product.id, variant_id=variant.id,
                     product_snapshot_json={"name": product.name}, quantity=1, unit_price=100,
                     status=item_status)
    db_session.add(item)
    db_session.commit()
    return order, item


def test_eligible_order_items_only_returns_recent_completed_normal_items(db_session):
    from app.commerce_service import eligible_order_items

    now = datetime(2026, 9, 7, 12, 0, 0)
    user = User(username="eligible-owner", password_hash="unused", role=Role.CUSTOMER)
    other = User(username="eligible-other", password_hash="unused", role=Role.CUSTOMER)
    db_session.add_all([user, other])
    db_session.commit()

    _completed, eligible = _order_with_item(db_session, user, "O-eligible", OrderStatus.COMPLETED, now - timedelta(days=1))
    _order_with_item(db_session, user, "O-old", OrderStatus.COMPLETED, now - timedelta(days=181))
    _order_with_item(db_session, user, "O-paid", OrderStatus.PAID_SIMULATED, now - timedelta(days=1))
    partial_order, _returned = _order_with_item(
        db_session, user, "O-returning", OrderStatus.RETURNING, now - timedelta(days=1), OrderItemStatus.RETURN_REQUESTED
    )
    partial_normal = OrderItem(
        order_id=partial_order.id,
        product_id=eligible.product_id,
        variant_id=eligible.variant_id,
        product_snapshot_json={"name": "未退款明细"},
        quantity=1,
        unit_price=100,
        status=OrderItemStatus.NORMAL,
    )
    db_session.add(partial_normal)
    db_session.commit()
    _order_with_item(db_session, other, "O-other", OrderStatus.COMPLETED, now - timedelta(days=1))

    assert eligible_order_items(db_session, user.id, now - timedelta(days=180)) == [eligible, partial_normal]


def test_eligible_order_items_excludes_fully_refunded_order(db_session):
    from app.commerce_service import eligible_order_items

    now = datetime(2026, 9, 7, 12, 0, 0)
    user = User(username="fully-refunded-owner", password_hash="unused", role=Role.CUSTOMER)
    db_session.add(user)
    db_session.commit()

    _order_with_item(
        db_session, user, "O-fully-refunded", OrderStatus.RETURNING, now - timedelta(days=1), OrderItemStatus.RETURN_REQUESTED
    )

    assert eligible_order_items(db_session, user.id, now - timedelta(days=180)) == []


def test_complete_order_transitions_paid_order_idempotently_and_is_owner_isolated(client, db_session):
    owner = User(username="complete-owner", password_hash="unused", role=Role.CUSTOMER)
    other = User(username="complete-other", password_hash="unused", role=Role.CUSTOMER)
    db_session.add_all([owner, other])
    db_session.commit()
    order, _item = _order_with_item(db_session, owner, "O-complete", OrderStatus.PAID_SIMULATED, datetime(2026, 9, 7))
    owner_headers = {"Authorization": f"Bearer {create_access_token(owner.id, owner.role.value)}"}
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id, other.role.value)}"}

    completed = client.post(f"/api/shop/orders/{order.id}/complete", headers=owner_headers)
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"

    replay = client.post(f"/api/shop/orders/{order.id}/complete", headers=owner_headers)
    assert replay.status_code == 200
    assert replay.json()["status"] == "COMPLETED"

    isolated = client.post(f"/api/shop/orders/{order.id}/complete", headers=other_headers)
    assert isolated.status_code == 404
