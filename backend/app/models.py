"""SQLAlchemy 数据模型。

三方对齐（2026-08-17）A-02：
- Decision 枚举必须包含 FAILED。
- Ticket 必须包含 error_code / error_message。
- 失败语义 = COMPLETED + FAILED + error_code + error_message。
"""
import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, enum.Enum):
    CS = "cs"        # 客服 CUSTOMER_SERVICE
    SV = "sv"        # 主管 SUPERVISOR


class TicketStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    SUSPENDED = "SUSPENDED"
    COMPLETED = "COMPLETED"


class Decision(str, enum.Enum):
    PENDING = "PENDING"
    AUTO_REFUNDED = "AUTO_REFUNDED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"          # A-02：错误语义


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.CS)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_no: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    image_paths: Mapped[list] = mapped_column(JSON, default=list)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    fraud_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.RUNNING)
    decision: Mapped[Decision] = mapped_column(Enum(Decision), default=Decision.PENDING)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)     # A-02
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)        # A-02
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    approvals: Mapped[list["Approval"]] = relationship(back_populates="ticket")
    traces: Mapped[list["AgentTrace"]] = relationship(back_populates="ticket")
    evaluations: Mapped[list["AgentEvaluationRun"]] = relationship(back_populates="ticket")


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(16))       # APPROVE / REJECT
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ticket: Mapped[Ticket] = relationship(back_populates="approvals")


class AgentTrace(Base):
    __tablename__ = "agent_traces"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    sequence_no: Mapped[int] = mapped_column(Integer, default=0)
    agent_name: Mapped[str] = mapped_column(String(32))   # Intake/OCR/Fraud/Sentiment/Decision/HumanReview
    status: Mapped[str] = mapped_column(String(16))       # RUNNING/SUCCESS/SUSPENDED/FAILED
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ticket: Mapped[Ticket] = relationship(back_populates="traces")


# 独立模型仍需在应用启动时注册到 SQLAlchemy metadata；生产建表只执行显式迁移。
from app.evaluation.models import AgentEvaluationRun  # noqa: E402,F401
