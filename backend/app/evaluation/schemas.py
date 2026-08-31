from datetime import datetime

from pydantic import BaseModel

from app.evaluation.models import AgentEvaluationRun


class EvaluationRecordOut(BaseModel):
    id: int
    ticket_id: int
    run_id: str
    prompt_version: str
    provider: str
    measurement_type: str
    baseline_input_tokens: int | None
    current_input_tokens: int | None
    current_output_tokens: int | None
    current_total_tokens: int | None
    saved_tokens: int | None
    reduction_ratio: float | None
    correctness_score: float | None
    safety_score: float | None
    explainability_score: float | None
    evaluation_status: str
    latency_breakdown: dict
    decision_route: str | None
    reason_summary: str | None
    error_code: str | None
    created_at: datetime | None


def serialize_evaluation(row: AgentEvaluationRun) -> dict:
    return EvaluationRecordOut(
        id=row.id,
        ticket_id=row.ticket_id,
        run_id=row.run_id,
        prompt_version=row.prompt_version,
        provider=row.provider,
        measurement_type=row.measurement_type,
        baseline_input_tokens=row.baseline_input_tokens,
        current_input_tokens=row.current_input_tokens,
        current_output_tokens=row.current_output_tokens,
        current_total_tokens=row.current_total_tokens,
        saved_tokens=row.saved_tokens,
        reduction_ratio=float(row.reduction_ratio) if row.reduction_ratio is not None else None,
        correctness_score=float(row.correctness_score) if row.correctness_score is not None else None,
        safety_score=float(row.safety_score) if row.safety_score is not None else None,
        explainability_score=float(row.explainability_score) if row.explainability_score is not None else None,
        evaluation_status=row.evaluation_status,
        latency_breakdown=row.latency_breakdown or {},
        decision_route=row.decision_route,
        reason_summary=row.reason_summary,
        error_code=row.error_code,
        created_at=row.created_at,
    ).model_dump(mode="json")
