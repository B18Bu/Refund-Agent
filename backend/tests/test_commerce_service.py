"""电商领域模型约束测试。"""

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.commerce_models import (
    Address,
    CartItem,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    ProductStatus,
    ProductSource,
    ProductVariant,
    ReturnRequest,
    ScrapeRun,
)
from app.models import Decision, Role, Ticket, TicketStatus, User


def test_order_service_recalculates_total_from_variant_price(db_session):
    from app.commerce_service import calculate_order_total
    product = Product(brand="vivo", name="Y200", status=ProductStatus.ACTIVE)
    db_session.add(product)
    db_session.flush()
    variant = ProductVariant(product_id=product.id, sku="service-y200", variant_name="标准版", spec_json={}, price=1999, available=True)
    db_session.add(variant)
    db_session.flush()
    assert calculate_order_total([(variant, 2)]) == 3998


def test_commerce_tables_and_status_enums_are_registered(db_engine):
    tables = inspect(db_engine).get_table_names()
    assert {
        "products",
        "product_variants",
        "product_sources",
        "addresses",
        "cart_items",
        "orders",
        "order_items",
        "return_requests",
        "scrape_runs",
    }.issubset(tables)
    assert OrderStatus.PAID_SIMULATED.value == "PAID_SIMULATED"


def test_order_item_keeps_product_snapshot_and_unique_keys(db_session):
    user = User(username="buyer", password_hash="hash", role=Role.CS)
    product = Product(brand="vivo", name="X100", model="V2301", status="ACTIVE")
    variant = ProductVariant(
        product=product,
        sku="vivo-x100-12-256",
        variant_name="12GB+256GB",
        spec_json={"memory": "12GB"},
        price=3999,
    )
    db_session.add_all([user, product, variant])
    db_session.flush()

    order = Order(
        order_no="O-1",
        user_id=user.id,
        status=OrderStatus.CREATED,
        address_snapshot_json={"city": "深圳"},
        total_amount=3999,
        idempotency_key="order-key-1",
    )
    item = OrderItem(
        order=order,
        product_id=product.id,
        variant_id=variant.id,
        product_snapshot_json={"name": product.name, "price": 3999},
        quantity=1,
        unit_price=3999,
    )
    db_session.add(item)
    db_session.commit()
    assert db_session.get(OrderItem, item.id).product_snapshot_json["name"] == "X100"

    duplicate_order = Order(
        order_no="O-2",
        user_id=user.id,
        status=OrderStatus.CREATED,
        address_snapshot_json={},
        total_amount=1,
        idempotency_key="order-key-1",
    )
    db_session.add(duplicate_order)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_product_source_and_return_ticket_are_unique(db_session):
    user = User(username="buyer-2", password_hash="hash")
    product = Product(brand="OPPO", name="Find X", status="ACTIVE")
    ticket = Ticket(
        ticket_no="T-1",
        user_id=1,
        amount=10,
        status=TicketStatus.COMPLETED,
        decision=Decision.APPROVED,
    )
    db_session.add_all([user, product])
    db_session.flush()
    ticket.user_id = user.id
    db_session.add(ticket)
    db_session.flush()
    source = ProductSource(
        product_id=product.id,
        source_site="oppo",
        source_url="https://oppo.com/find",
        external_id="find-x",
    )
    db_session.add(source)
    db_session.commit()

    db_session.add(
        ProductSource(
            product_id=product.id,
            source_site="oppo",
            source_url="https://oppo.com/find-2",
            external_id="find-x",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_cart_item_is_unique_per_user_and_variant(db_session):
    user = User(username="cart-user", password_hash="hash")
    product = Product(brand="vivo", name="Y200", status="ACTIVE")
    variant = ProductVariant(
        product=product,
        sku="y200-default",
        variant_name="标准版",
        spec_json={},
        price=1999,
    )
    db_session.add_all([user, product, variant])
    db_session.flush()
    db_session.add(CartItem(user_id=user.id, variant_id=variant.id, quantity=1))
    db_session.commit()
    db_session.add(CartItem(user_id=user.id, variant_id=variant.id, quantity=2))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_return_request_ticket_id_is_unique(db_session):
    user = User(username="return-user", password_hash="hash")
    product = Product(brand="OPPO", name="Find X", status="ACTIVE")
    variant = ProductVariant(
        product=product,
        sku="find-x-return",
        variant_name="标准版",
        spec_json={},
        price=1,
    )
    ticket = Ticket(
        ticket_no="T-return",
        user_id=1,
        amount=1,
        status=TicketStatus.COMPLETED,
        decision=Decision.APPROVED,
    )
    db_session.add_all([user, product, variant])
    db_session.flush()
    ticket.user_id = user.id
    db_session.add(ticket)
    db_session.flush()
    order = Order(
        order_no="O-return",
        user_id=user.id,
        status=OrderStatus.PAID_SIMULATED,
        address_snapshot_json={},
        total_amount=1,
    )
    db_session.add(order)
    db_session.flush()
    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        variant_id=variant.id,
        product_snapshot_json={"name": product.name},
        quantity=1,
        unit_price=1,
    )
    db_session.add(item)
    db_session.flush()

    db_session.add(
        ReturnRequest(
            return_no="R-1",
            order_id=order.id,
            order_item_id=item.id,
            user_id=user.id,
            reason="质量问题",
            ticket_id=ticket.id,
        )
    )
    db_session.commit()
    db_session.add(
        ReturnRequest(
            return_no="R-2",
            order_id=order.id,
            order_item_id=item.id,
            user_id=user.id,
            reason="重复提交",
            ticket_id=ticket.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
