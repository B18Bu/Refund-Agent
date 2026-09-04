"""地址、购物车和订单领域服务。"""
import uuid
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.commerce_models import (Address, CartItem, Order, OrderItem, OrderItemStatus,
                                  OrderStatus, ProductStatus, ProductVariant, ReturnRequest,
                                  ReturnStatus)
from app.models import Decision, Ticket, TicketStatus
from app.config import settings


def calculate_order_total(items: list[tuple[ProductVariant, int]]) -> Decimal:
    return sum((Decimal(str(variant.price)) * quantity for variant, quantity in items), Decimal("0.00"))


def set_default_address(db: Session, user_id: int, address: Address) -> None:
    db.query(Address).filter(Address.user_id == user_id, Address.id != address.id).update(
        {Address.is_default: False}, synchronize_session=False
    )
    address.is_default = True


def create_order(db: Session, user_id: int, address_id: int, idempotency_key: str) -> Order:
    existing = db.query(Order).filter(Order.user_id == user_id, Order.idempotency_key == idempotency_key).first()
    if existing:
        return existing
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == user_id).first()
    if address is None:
        raise ValueError("收货地址不存在")
    cart = db.query(CartItem).filter(CartItem.user_id == user_id).with_for_update().all()
    if not cart:
        raise ValueError("购物车为空")
    variants = {}
    for item in cart:
        variant = (db.query(ProductVariant).options(joinedload(ProductVariant.product))
                   .filter(ProductVariant.id == item.variant_id).with_for_update().first())
        if variant is None or not variant.available or variant.product.status != ProductStatus.ACTIVE:
            raise ValueError("购物车中存在不可售商品")
        variants[item.variant_id] = variant
    total = calculate_order_total([(variants[item.variant_id], item.quantity) for item in cart])
    address_snapshot = {
        "recipient_name": address.recipient_name, "phone": address.phone,
        "province": address.province, "city": address.city, "district": address.district,
        "detail": address.detail,
    }
    order = Order(order_no=f"O{uuid.uuid4().hex.upper()}", user_id=user_id,
                  address_snapshot_json=address_snapshot, status=OrderStatus.CREATED,
                  total_amount=total, currency="CNY", idempotency_key=idempotency_key)
    db.add(order)
    for cart_item in cart:
        variant = variants[cart_item.variant_id]
        product = variant.product
        order.items.append(OrderItem(product_id=product.id, variant_id=variant.id,
            product_snapshot_json={"name": product.name, "brand": product.brand, "model": product.model,
                                   "variant_name": variant.variant_name, "sku": variant.sku,
                                   "spec_json": variant.spec_json or {}, "image_url": product.image_url},
            quantity=cart_item.quantity, unit_price=variant.price))
    try:
        db.flush()
        for cart_item in cart:
            db.delete(cart_item)
        db.commit()
        db.refresh(order)
        return order
    except IntegrityError:
        db.rollback()
        existing = db.query(Order).filter(Order.user_id == user_id, Order.idempotency_key == idempotency_key).first()
        if existing:
            return existing
        raise


def simulate_payment(db: Session, user_id: int, order_id: int) -> Order:
    """将本用户的 CREATED 订单原子地标记为模拟支付成功。

    不接触任何外部支付服务；重复请求对已支付订单幂等返回。
    """
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if order is None:
        raise LookupError("订单不存在")
    if order.status == OrderStatus.PAID_SIMULATED:
        return order
    if order.status != OrderStatus.CREATED:
        raise ValueError("订单当前状态不可支付")

    # 条件更新避免并发请求将其他状态覆盖为已支付。
    changed = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == user_id,
        Order.status == OrderStatus.CREATED,
    ).update({Order.status: OrderStatus.PAID_SIMULATED}, synchronize_session=False)
    if changed:
        db.commit()
        db.refresh(order)
        return order

    # 另一请求可能已完成支付，重新读取以保持幂等；其他状态必须拒绝。
    db.rollback()
    current = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if current is None:
        raise LookupError("订单不存在")
    if current.status == OrderStatus.PAID_SIMULATED:
        return current
    raise ValueError("订单当前状态不可支付")


def map_ticket_to_return_status(ticket_status, decision) -> ReturnStatus:
    """将后台工单状态确定性映射为用户退单状态。"""
    status = getattr(ticket_status, "value", ticket_status)
    outcome = getattr(decision, "value", decision)
    if outcome == "FAILED":
        return ReturnStatus.FAILED
    if outcome in ("AUTO_REFUNDED", "APPROVED"):
        return ReturnStatus.APPROVED
    if outcome == "REJECTED":
        return ReturnStatus.REJECTED
    if outcome == "PENDING" and status == "SUSPENDED":
        return ReturnStatus.PENDING_REVIEW
    return ReturnStatus.PROCESSING


def create_return_request(db: Session, user_id: int, order_id: int, order_item_id: int,
                          reason: str, description: str | None, evidence_paths: list[str],
                          idempotency_key: str, redis) -> ReturnRequest:
    existing = db.query(ReturnRequest).filter(ReturnRequest.user_id == user_id,
                                               ReturnRequest.idempotency_key == idempotency_key).first()
    if existing:
        return existing
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if order is None:
        raise LookupError("订单不存在")
    if order.status != OrderStatus.PAID_SIMULATED:
        raise ValueError("仅已模拟支付订单可申请退单")
    item = db.query(OrderItem).filter(OrderItem.id == order_item_id, OrderItem.order_id == order_id).with_for_update().first()
    if item is None:
        raise LookupError("订单明细不存在")
    if item.status != OrderItemStatus.NORMAL:
        raise ValueError("该订单明细已申请退单")
    amount = Decimal(str(item.unit_price)) * item.quantity
    ticket = Ticket(ticket_no=uuid.uuid4().hex, user_id=user_id, amount=amount,
                    image_paths=evidence_paths or [], description=description,
                    status=TicketStatus.RUNNING,
                    decision=Decision.PENDING, thread_id=uuid.uuid4().hex,
                    idempotency_key=f"return:{idempotency_key}")
    rr = ReturnRequest(return_no=f"R{uuid.uuid4().hex.upper()}", order_id=order_id,
                       order_item_id=order_item_id, user_id=user_id, reason=reason.strip(),
                       description=description, evidence_paths=evidence_paths or [],
                       status=ReturnStatus.SUBMITTED, idempotency_key=idempotency_key)
    db.add(ticket)
    db.add(rr)
    db.flush()
    rr.ticket_id = ticket.id
    item.status = OrderItemStatus.RETURN_REQUESTED
    order.status = OrderStatus.RETURNING
    db.commit()
    try:
        redis.xadd(settings.STREAM_KEY, {"type": "START", "ticket_id": str(ticket.id), "thread_id": ticket.thread_id})
    except Exception as exc:
        db.rollback()
        rr = db.get(ReturnRequest, rr.id)
        ticket = db.get(Ticket, ticket.id)
        if rr is not None:
            rr.status = ReturnStatus.FAILED
            rr.error_code = "QUEUE_PUBLISH_FAILED"
            rr.error_message = str(exc)[:2000]
        if ticket is not None:
            ticket.status = TicketStatus.COMPLETED
            ticket.decision = Decision.FAILED
            ticket.error_code = "QUEUE_PUBLISH_FAILED"
            ticket.error_message = str(exc)[:2000]
        db.commit()
    db.refresh(rr)
    return rr
