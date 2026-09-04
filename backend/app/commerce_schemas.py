"""电商商品及目录响应模型。"""
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProductDTO(BaseModel):
    brand: str = Field(min_length=1, max_length=64)
    sku: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(gt=0)
    source_url: HttpUrl
    model: str | None = None
    description: str | None = None
    image_url: str | None = None
    variant_name: str = "标准版"
    spec_json: dict = Field(default_factory=dict)
    external_id: str | None = None

    @field_validator("brand", "sku", "name", mode="before")
    @classmethod
    def strip_required(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("字段不能为空")
        return value.strip()

    @field_validator("source_url")
    @classmethod
    def require_https(cls, value: HttpUrl):
        if value.scheme != "https":
            raise ValueError("source_url 必须使用 HTTPS")
        return value


class ProductVariantOut(BaseModel):
    id: int
    sku: str
    variant_name: str
    spec_json: dict
    price: float
    currency: str
    available: bool


class ProductOut(BaseModel):
    id: int
    brand: str
    name: str
    model: str | None = None
    description: str | None = None
    source_url: str | None = None
    source_site: str | None = None
    image_url: str | None = None
    status: str
    variants: list[ProductVariantOut] = Field(default_factory=list)


class ProductPage(BaseModel):
    items: list[ProductOut]
    page: int
    page_size: int
    total: int


class AddressCreate(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=64)
    phone: str = Field(min_length=1, max_length=32)
    province: str = Field(min_length=1, max_length=64)
    city: str = Field(min_length=1, max_length=64)
    district: str = Field(min_length=1, max_length=64)
    detail: str = Field(min_length=1, max_length=255)
    is_default: bool = False


class AddressUpdate(AddressCreate):
    pass


class AddressOut(AddressCreate):
    id: int

    model_config = {"from_attributes": True}


class CartItemUpsert(BaseModel):
    quantity: int = Field(gt=0)


class CartItemOut(BaseModel):
    id: int
    variant_id: int
    quantity: int
    sku: str
    variant_name: str
    price: float
    product_id: int
    product_name: str
    brand: str


class OrderCreate(BaseModel):
    address_id: int = Field(gt=0)


class SimulatePaymentRequest(BaseModel):
    """模拟支付不接收任何真实支付凭据。"""

    model_config = ConfigDict(extra="forbid")


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    variant_id: int
    product_snapshot_json: dict
    quantity: int
    unit_price: float
    status: str


class OrderOut(BaseModel):
    id: int
    order_no: str
    status: str
    total_amount: float
    currency: str
    address_snapshot_json: dict
    items: list[OrderItemOut] = Field(default_factory=list)


class ReturnCreate(BaseModel):
    order_item_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=4000)
    evidence_paths: list[str] = Field(default_factory=list, max_length=3)


class ReturnOut(BaseModel):
    id: int
    return_no: str
    order_id: int
    order_item_id: int
    status: str
    reason: str
    description: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    ticket_id: int | None = None
    error_code: str | None = None
