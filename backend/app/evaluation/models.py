from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AgentEvaluationRun(Base):
    """一次工单首次决策运行产生的脱敏评测记录。"""

    __tablename__ = "agent_evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    prompt_version: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    measurement_type: Mapped[str] = mapped_column(String(16))
    baseline_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saved_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reduction_ratio: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    correctness_score: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    safety_score: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    explainability_score: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    evaluation_status: Mapped[str] = mapped_column(String(16))
    latency_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    decision_route: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ticket: Mapped["Ticket"] = relationship(back_populates="evaluations")
