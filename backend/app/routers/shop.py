"""用户端商品目录只读接口。"""
import os
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from app.commerce_models import Address, CartItem, Order, OrderItem, Product, ProductStatus, ProductVariant, ReturnRequest
from app.commerce_schemas import (AddressCreate, AddressOut, AddressUpdate, CartItemOut, CartItemUpsert,
                                   OrderCreate, OrderOut, OrderItemOut, ProductOut, ProductPage, ProductVariantOut,
                                   SimulatePaymentRequest, ReturnCreate, ReturnOut)
from app.commerce_service import (create_order, set_default_address, simulate_payment,
                                   create_return_request, map_ticket_to_return_status)
from app.deps import get_db, require_roles
from app.models import Role, Ticket
from app.redis_client import get_redis
from app.idempotency import resolve_idempotency
from app.catalog_initialization import catalog_is_ready
from app.storage import resolve_abs_path, save_upload

router = APIRouter(prefix="/api/shop", tags=["shop"])


def _variant(v: ProductVariant) -> ProductVariantOut:
    return ProductVariantOut(id=v.id, sku=v.sku, variant_name=v.variant_name,
                             spec_json=v.spec_json or {}, price=float(v.price), currency=v.currency,
                             available=v.available)


def _product(p: Product) -> ProductOut:
    return ProductOut(id=p.id, brand=p.brand, name=p.name, model=p.model,
                      description=p.description, source_url=p.source_url,
                      source_site=p.source_site, image_url=p.image_url,
                      status=p.status.value if hasattr(p.status, "value") else str(p.status),
                      variants=[_variant(v) for v in p.variants])


@router.get("/products", response_model=ProductPage)
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    brand: str | None = None,
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    db: Session = Depends(get_db),
):
    if not catalog_is_ready(db):
        raise HTTPException(503, detail={"code": "CATALOG_NOT_READY", "message": "商品目录尚未完成首次抓取"})
    query = db.query(Product).options(joinedload(Product.variants)).filter(Product.status == ProductStatus.ACTIVE)
    if keyword:
        term = f"%{keyword.strip()}%"
        query = query.filter((Product.name.ilike(term)) | (Product.model.ilike(term)))
    if brand:
        query = query.filter(func.lower(Product.brand) == brand.strip().lower())
    if min_price is not None or max_price is not None:
        query = query.join(ProductVariant).filter(ProductVariant.available.is_(True))
        if min_price is not None:
            query = query.filter(ProductVariant.price >= min_price)
        if max_price is not None:
            query = query.filter(ProductVariant.price <= max_price)
        query = query.distinct()
    total = query.order_by(None).count()
    rows = query.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ProductPage(items=[_product(row) for row in rows], page=page, page_size=page_size, total=total)


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    if not catalog_is_ready(db):
        raise HTTPException(503, detail={"code": "CATALOG_NOT_READY", "message": "商品目录尚未完成首次抓取"})
    product = (db.query(Product).options(joinedload(Product.variants))
               .filter(Product.id == product_id, Product.status == ProductStatus.ACTIVE).first())
    if product is None:
        raise HTTPException(404, "商品不存在")
    return _product(product)


@router.get("/brands", response_model=list[str])
def list_brands(db: Session = Depends(get_db)):
    if not catalog_is_ready(db):
        raise HTTPException(503, detail={"code": "CATALOG_NOT_READY", "message": "商品目录尚未完成首次抓取"})
    rows = (db.query(Product.brand).filter(Product.status == ProductStatus.ACTIVE)
            .distinct().order_by(Product.brand).all())
    return [row[0] for row in rows]


def _address_out(address: Address) -> dict:
    return {"id": address.id, "recipient_name": address.recipient_name, "phone": address.phone,
            "province": address.province, "city": address.city, "district": address.district,
            "detail": address.detail, "is_default": address.is_default}


def _cart_out(item: CartItem, variant: ProductVariant) -> dict:
    return {"id": item.id, "variant_id": variant.id, "quantity": item.quantity, "sku": variant.sku,
            "variant_name": variant.variant_name, "price": float(variant.price),
            "product_id": variant.product.id, "product_name": variant.product.name, "brand": variant.product.brand}


def _order_out(order: Order) -> dict:
    return {"id": order.id, "order_no": order.order_no, "status": order.status.value,
            "total_amount": float(order.total_amount), "currency": order.currency,
            "address_snapshot_json": order.address_snapshot_json, "items": [
                {"id": i.id, "product_id": i.product_id, "variant_id": i.variant_id,
                 "product_snapshot_json": i.product_snapshot_json, "quantity": i.quantity,
                 "unit_price": float(i.unit_price), "status": i.status.value} for i in order.items]}


@router.get("/addresses", response_model=list[AddressOut])
def list_addresses(user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    return [_address_out(a) for a in db.query(Address).filter(Address.user_id == user.id).order_by(Address.id).all()]


@router.post("/addresses", response_model=AddressOut, status_code=201)
def add_address(body: AddressCreate, user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    has_existing = db.query(Address.id).filter(Address.user_id == user.id).first() is not None
    address = Address(user_id=user.id, **body.model_dump())
    if body.is_default or not has_existing:
        set_default_address(db, user.id, address)
    db.add(address)
    db.flush()
    db.commit()
    db.refresh(address)
    return _address_out(address)


@router.get("/addresses/{address_id}", response_model=AddressOut)
def get_address(address_id: int, user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == user.id).first()
    if address is None:
        raise HTTPException(404, "地址不存在")
    return _address_out(address)


@router.put("/addresses/{address_id}", response_model=AddressOut)
def update_address(address_id: int, body: AddressUpdate, user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == user.id).first()
    if address is None:
        raise HTTPException(404, "地址不存在")
    for key, value in body.model_dump().items():
        setattr(address, key, value)
    if body.is_default:
        set_default_address(db, user.id, address)
    db.commit()
    db.refresh(address)
    return _address_out(address)


@router.delete("/addresses/{address_id}", status_code=204)
def delete_address(address_id: int, user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    address = db.query(Address).filter(Address.id == address_id, Address.user_id == user.id).first()
    if address is None:
        raise HTTPException(404, "地址不存在")
    was_default = address.is_default
    db.delete(address)
    db.flush()
    if was_default:
        replacement = db.query(Address).filter(Address.user_id == user.id).order_by(Address.id).first()
        if replacement:
            replacement.is_default = True
    db.commit()


@router.get("/cart")
def get_cart(user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    rows = db.query(CartItem).filter(CartItem.user_id == user.id).all()
    result = []
    for row in rows:
        variant = db.query(ProductVariant).options(joinedload(ProductVariant.product)).get(row.variant_id)
        if variant is not None:
            result.append(_cart_out(row, variant))
    return {"items": result, "total_amount": sum(x["price"] * x["quantity"] for x in result)}


@router.put("/cart/items/{variant_id}")
def upsert_cart_item(variant_id: int, body: CartItemUpsert, user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    variant = db.query(ProductVariant).options(joinedload(ProductVariant.product)).filter(ProductVariant.id == variant_id).first()
    if variant is None or not variant.available or variant.product.status != ProductStatus.ACTIVE:
        raise HTTPException(409, "商品规格不存在或不可售")
    item = db.query(CartItem).filter(CartItem.user_id == user.id, CartItem.variant_id == variant_id).first()
    if item is None:
        item = CartItem(user_id=user.id, variant_id=variant_id, quantity=body.quantity)
        db.add(item)
    else:
        item.quantity = body.quantity
    db.commit()
    db.refresh(item)
    return _cart_out(item, variant)


@router.delete("/cart/items/{variant_id}", status_code=204)
def delete_cart_item(variant_id: int, user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    item = db.query(CartItem).filter(CartItem.user_id == user.id, CartItem.variant_id == variant_id).first()
    if item is not None:
        db.delete(item)
        db.commit()


@router.post("/orders", response_model=OrderOut, status_code=201)
def add_order(body: OrderCreate, user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db),
              x_idempotency_key: str | None = Header(None)):
    if not x_idempotency_key or not x_idempotency_key.strip():
        raise HTTPException(400, "必须提供 X-Idempotency-Key")
    try:
        order = create_order(db, user.id, body.address_id, x_idempotency_key.strip())
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return _order_out(order)


@router.post("/orders/{order_id}/simulate-pay", response_model=OrderOut)
def simulate_order_payment(order_id: int, body: SimulatePaymentRequest | None = None,
                           user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    try:
        order = simulate_payment(db, user.id, order_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return _order_out(order)


@router.get("/orders", response_model=list[OrderOut])
def list_orders(user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    rows = db.query(Order).options(joinedload(Order.items)).filter(Order.user_id == user.id).order_by(Order.id.desc()).all()
    return [_order_out(row) for row in rows]


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id, Order.user_id == user.id).first()
    if order is None:
        raise HTTPException(404, "订单不存在")
    return _order_out(order)


def _return_out(row: ReturnRequest, db: Session) -> dict:
    ticket = db.get(Ticket, row.ticket_id) if row.ticket_id else None
    if ticket is not None:
        mapped = map_ticket_to_return_status(ticket.status, ticket.decision)
        if row.status != mapped:
            row.status = mapped
            db.commit()
    return {"id": row.id, "return_no": row.return_no, "order_id": row.order_id,
            "order_item_id": row.order_item_id, "status": row.status.value,
            "reason": row.reason, "description": row.description,
            "evidence_paths": row.evidence_paths or [], "ticket_id": row.ticket_id,
            "error_code": row.error_code}


def _validate_controlled_evidence_paths(evidence_paths: list[str]) -> None:
    """仅接受已由本服务保存且仍存在的凭证键，拒绝客户端文件名。"""
    for storage_key in evidence_paths:
        if not storage_key.startswith("uploads/") or not storage_key.lower().endswith((".jpg", ".jpeg", ".png")):
            raise HTTPException(422, "凭证必须先通过上传接口保存")
        if not os.path.isfile(resolve_abs_path(storage_key)):
            raise HTTPException(422, "凭证不存在或不可用")


@router.post("/return-evidence", status_code=201)
async def upload_return_evidence(
    files: list[UploadFile] = File(...),
    _user=Depends(require_roles(Role.CUSTOMER)),
):
    """先持久化受控凭证，再允许客户创建退款，避免 Worker 读取到本地文件名。"""
    if not files:
        raise HTTPException(400, "至少上传一张凭证图片")
    if len(files) > 3:
        raise HTTPException(413, "最多上传 3 张图片")
    storage_keys = [(await save_upload(upload))["storage_key"] for upload in files]
    return {"storage_keys": storage_keys}


@router.post("/orders/{order_id}/returns", response_model=ReturnOut, status_code=201)
def create_order_return(order_id: int, body: ReturnCreate, response: Response,
                        user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db),
                        redis=Depends(get_redis), x_idempotency_key: str | None = Header(None)):
    if not x_idempotency_key or not x_idempotency_key.strip():
        raise HTTPException(400, "必须提供 X-Idempotency-Key")
    key = x_idempotency_key.strip()

    # 数据库记录优先于业务状态校验，确保已完成请求可安全重放（此时明细已是
    # RETURN_REQUESTED），同时避免重复创建 Ticket。
    existing_db = db.query(ReturnRequest).filter(
        ReturnRequest.user_id == user.id, ReturnRequest.idempotency_key == key
    ).first()
    if existing_db is not None:
        if existing_db.status.value == "FAILED":
            response.status_code = 200
        return _return_out(existing_db, db)

    if not body.reason.strip():
        raise HTTPException(422, "必须填写退款原因")
    _validate_controlled_evidence_paths(body.evidence_paths)

    # 先做确定性业务校验，再占用 Redis 幂等键；否则校验失败会留下“幽灵”键，
    # 后续使用同一幂等键的合法请求将被错误地判定为处理中。
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if order is None:
        raise HTTPException(404, "订单不存在")
    if order.status.value != "PAID_SIMULATED":
        raise HTTPException(409, "仅已模拟支付订单可申请退单")
    item = db.query(OrderItem).filter(OrderItem.id == body.order_item_id,
                                      OrderItem.order_id == order_id).first()
    if item is None:
        raise HTTPException(404, "订单明细不存在")
    if item.status.value != "NORMAL":
        raise HTTPException(409, "该订单明细已申请退单")

    idem_existing = resolve_idempotency(redis, f"idem:return:{user.id}:{key}", key)
    if idem_existing is not None:
        existing = db.query(ReturnRequest).filter(ReturnRequest.user_id == user.id,
                                                   ReturnRequest.idempotency_key == key).first()
        if existing is None:
            raise HTTPException(409, "退单请求正在处理中")
        if existing.status.value == "FAILED":
            response.status_code = 200
        return _return_out(existing, db)
    try:
        row = create_return_request(db, user.id, order_id, body.order_item_id, body.reason,
                                    body.description, body.evidence_paths, key, redis)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if row.status.value == "FAILED":
        raise HTTPException(503, "退单工单投递失败，请使用相同幂等键查询失败状态")
    return _return_out(row, db)


@router.get("/returns", response_model=list[ReturnOut])
def list_returns(user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    rows = db.query(ReturnRequest).filter(ReturnRequest.user_id == user.id).order_by(ReturnRequest.id.desc()).all()
    return [_return_out(row, db) for row in rows]


@router.get("/returns/{return_id}", response_model=ReturnOut)
def get_return(return_id: int, user=Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    row = db.query(ReturnRequest).filter(ReturnRequest.id == return_id, ReturnRequest.user_id == user.id).first()
    if row is None:
        raise HTTPException(404, "退单不存在")
    return _return_out(row, db)
