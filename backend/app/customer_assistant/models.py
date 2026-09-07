"""消费者偏好的最小可审计数据模型。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


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
