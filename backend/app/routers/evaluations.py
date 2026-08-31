import json
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db, require_role
from app.evaluation.models import AgentEvaluationRun
from app.evaluation.schemas import serialize_evaluation
from app.models import Role

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _average(values) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    return sum(numbers) / len(numbers) if numbers else None


def _golden_summary() -> dict:
    path = Path(settings.GOLDEN_REPORT_PATH)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"available": False}
    return {
        "available": True,
        "case_count": int(payload.get("case_count", 0)),
        "passed": bool(payload.get("passed", False)),
        "score": int(payload.get("score", 0)),
        "max_score": int(payload.get("max_score", 0)),
    }


@router.get("/summary")
def get_evaluation_summary(
    _user=Depends(require_role(Role.SV)),
    db: Session = Depends(get_db),
):
    rows = db.query(AgentEvaluationRun).order_by(AgentEvaluationRun.id.desc()).all()
    trend_groups: dict[str, list[AgentEvaluationRun]] = defaultdict(list)
    for row in rows:
        if row.created_at:
            trend_groups[row.created_at.date().isoformat()].append(row)
    trend = [
        {
            "date": day,
            "baseline_input_tokens": _average(row.baseline_input_tokens for row in group),
            "current_input_tokens": _average(row.current_input_tokens for row in group),
            "count": len(group),
        }
        for day, group in sorted(trend_groups.items())[-7:]
    ]
    token_rows = [
        row for row in rows
        if row.baseline_input_tokens is not None and row.current_input_tokens is not None
    ]
    score_rows = [row for row in rows if row.correctness_score is not None]
    return {
        "evaluation_count": len(rows),
        "avg_baseline_input_tokens": _average(row.baseline_input_tokens for row in token_rows),
        "avg_current_input_tokens": _average(row.current_input_tokens for row in token_rows),
        "avg_saved_tokens": _average(row.saved_tokens for row in token_rows),
        "avg_reduction_ratio": _average(row.reduction_ratio for row in token_rows),
        "average_scores": {
            "correctness": _average(row.correctness_score for row in score_rows),
            "safety": _average(row.safety_score for row in score_rows),
            "explainability": _average(row.explainability_score for row in score_rows),
        },
        "data_completeness": {
            "token_records": len(token_rows),
            "score_records": len(score_rows),
        },
        "measurement_types": sorted({row.measurement_type for row in rows}),
        "trend": trend,
        "recent": [serialize_evaluation(row) for row in rows[:20]],
        "golden": _golden_summary(),
    }
