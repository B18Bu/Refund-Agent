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
from app.agents.intent import IntentFilter

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


@router.get("/orchestration")
def get_orchestration_snapshot(_user=Depends(require_role(Role.SV))):
    """返回工单 8 编排评测快照，仅读取样本和本地报告。"""
    root = Path(__file__).resolve().parents[3]
    sample_path = root / "evals" / "intent" / "intent_samples.jsonl"
    samples = []
    if sample_path.exists():
        for line in sample_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    samples.append(json.loads(line))
                except ValueError:
                    continue
    strong_signal = sum(
        1 for sample in samples
        if IntentFilter().classify(str(sample.get("text", ""))).route == "strong_signal"
    )
    report_json_path = root / "artifacts" / "ab-benchmark-report.json"
    report_data = {}
    try:
        report_data = json.loads(report_json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        report_data = {}
    report_path = root / "docs" / "evidence" / "ab-benchmark-report.md"
    report = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    import re
    reduction = re.search(r"Token 降低率：([0-9.]+)%", report)
    hybrid = re.search(r"\| 双层混合流 \| (\d+)", report)
    pure = re.search(r"\| 纯 LLM \| (\d+)", report)
    return {
        "pipeline": [
            {"key": key, "label": label}
            for key, label in (("intake", "接收"), ("ocr", "OCR"), ("critic", "安全网关"),
                               ("intent", "意图识别"), ("risk", "风险评估"),
                               ("fallback", "异常兜底"), ("decision", "确定性决策"))
        ],
        "intent": {"sample_count": len(samples), "strong_signal": strong_signal,
                   "llm_judge": max(0, len(samples) - strong_signal),
                   "coverage": 1.0 if samples else 0.0},
        "fallback": {"reasons": ["llm_call_failed", "llm_output_parse_fallback"], "audited": True},
        "ab": {"pure_tokens": int(pure.group(1)) if pure else None,
               "hybrid_tokens": int(hybrid.group(1)) if hybrid else None,
               "token_reduction": report_data.get("token_reduction", float(reduction.group(1)) / 100 if reduction else None),
               "report_available": bool(report or report_data)},
    }
