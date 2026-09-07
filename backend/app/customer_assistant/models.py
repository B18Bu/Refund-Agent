"""消费者助手的最小可审计数据模型。"""

import json
import math
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.db import Base


class CustomerCatalogVector(UserDefinedType):
    """消费者商品索引专用的固定维度向量列。"""

    cache_ok = True

    def get_col_spec(self, **_kwargs) -> str:
        return "VECTOR(512)"

    def bind_processor(self, _dialect):
        def process(value):
            vector = self._validate(value)
            return None if vector is None else "[" + ",".join(repr(item) for item in vector) + "]"

        return process

    def result_processor(self, _dialect, _coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            return self._validate(json.loads(value) if isinstance(value, str) else value)

        return process

    @staticmethod
    def _validate(value):
        if value is None:
            return None
        if not isinstance(value, list) or len(value) != 512:
            raise ValueError("embedding 必须是长度为 512 的列表")
        if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in value):
            raise ValueError("embedding 必须只包含有限数值")
        return [float(item) for item in value]


class CustomerPrivacySetting(Base):
    __tablename__ = "customer_privacy_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CustomerPreference(Base):
    __tablename__ = "customer_preferences"
    __table_args__ = (UniqueConstraint("user_id", "preference_key", name="uq_customer_preferences_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    preference_key: Mapped[str] = mapped_column(String(64))
    automatic_value: Mapped[list | None] = mapped_column(JSON, nullable=True)
    manual_value: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_order_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class IgnoredPreference(Base):
    __tablename__ = "customer_preference_ignores"
    __table_args__ = (UniqueConstraint("user_id", "preference_key", name="uq_customer_preference_ignores_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    preference_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CustomerPreferenceAudit(Base):
    """偏好操作审计；摘要只描述结构，不保存偏好原值。"""

    __tablename__ = "customer_preference_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(32))
    preference_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CustomerCatalogChunk(Base):
    """与主管政策 RAG 完全隔离的商品检索分块。"""

    __tablename__ = "customer_catalog_chunks"
    __table_args__ = (
        UniqueConstraint("product_id", "source_url", "content_hash", name="uq_customer_catalog_chunks_source_content"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    source_url: Mapped[str] = mapped_column(String(1024))
    crawled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_hash: Mapped[str] = mapped_column(String(128), index=True)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float]] = mapped_column(CustomerCatalogVector())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
