import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError

from app import models as _models  # noqa: F401  # 注册 Ticket 与双向关系
from app.agents.prompts import estimate_prompt_tokens, legacy_prompt, sentiment_input_text
from app.config import settings
from app.db import SessionLocal
from app.evaluation.models import AgentEvaluationRun
from app.evaluation.scoring import calculate_token_delta, score_evaluation

logger = logging.getLogger(__name__)


def should_record_evaluation(message_type: str) -> bool:
    return message_type.upper() == "START"


def try_persist_evaluation(operation: Callable[[], Any]) -> bool:
    try:
        operation()
        return True
    except IntegrityError as exc:
        if _is_duplicate_run_id(exc):
            logger.info("评测记录已存在，按幂等命中处理")
            return True
        logger.warning("评测记录完整性校验失败，不影响审批结果: %s", exc)
        return False
    except Exception as exc:
        logger.warning("评测记录写入失败，不影响审批结果: %s", exc)
        return False


def _is_duplicate_run_id(exc: IntegrityError) -> bool:
    orig = exc.orig
    constraint_name = getattr(getattr(orig, "diag", None), "constraint_name", None)
    if constraint_name == "ux_agent_evaluation_runs_run_id":
        return True
    message = str(orig).lower()
    return "unique" in message and (
        "agent_evaluation_runs.run_id" in message
        or "ux_agent_evaluation_runs_run_id" in message
    )


def build_evaluation(*, ticket_id: int, run_id: str, state: dict) -> AgentEvaluationRun:
    usage_items = list((state.get("token_usage") or {}).values())
    current_input = sum(int(item.get("input_tokens", 0)) for item in usage_items)
    current_output = sum(int(item.get("output_tokens", 0)) for item in usage_items)
    current_total = sum(int(item.get("total_tokens", 0)) for item in usage_items)
    measurement_types = {str(item.get("measurement_type", "estimated")) for item in usage_items}
    if len(measurement_types) > 1:
        measurement_type = "mixed"
    elif measurement_types:
        measurement_type = measurement_types.pop()
    else:
        measurement_type = "estimated"

    material = f"退款金额：{state.get('amount')}\n凭证 OCR：{state.get('ocr_text', '')}"
    sentiment_material = state.get("ocr_text", "") or f"客诉金额：{state.get('amount')}"
    baseline_input = (
        estimate_prompt_tokens(legacy_prompt(material))
        + estimate_prompt_tokens(sentiment_input_text(sentiment_material))
    )
    token_delta = calculate_token_delta(baseline_input, current_input)
    reasons = [str(reason) for reason in state.get("decision_reasons", [])]
    scores = score_evaluation(
        amount=float(state.get("amount", 0)),
        ocr_confidence=float(state.get("ocr_confidence", 0)),
        fraud_score=int(state.get("fraud_score", 100)),
        sentiment=str(state.get("sentiment", "HIGH")),
        actual_route=state.get("decision"),
        reasons=reasons,
    )
    latency = {
        str(key): float(value)
        for key, value in (state.get("latency_breakdown") or {}).items()
        if str(key).endswith("_ms") and isinstance(value, (int, float))
    }
    status = "PENDING" if scores.correctness is None else (
        "PASSED" if scores.correctness == 2 and scores.safety == 2 else "FAILED"
    )
    return AgentEvaluationRun(
        ticket_id=ticket_id,
        run_id=run_id,
        prompt_version=getattr(settings, "PROMPT_VERSION", "refund-v1"),
        provider=settings.LLM_PROVIDER,
        measurement_type=measurement_type,
        baseline_input_tokens=baseline_input,
        current_input_tokens=current_input,
        current_output_tokens=current_output,
        current_total_tokens=current_total,
        saved_tokens=token_delta.saved_tokens,
        reduction_ratio=token_delta.reduction_ratio,
        correctness_score=scores.correctness,
        safety_score=scores.safety,
        explainability_score=scores.explainability,
        evaluation_status=status,
        latency_breakdown=latency,
        decision_route=state.get("decision"),
        reason_summary=",".join(reasons)[:1000] or None,
        error_code=None,
    )


def record_evaluation(*, ticket_id: int, run_id: str, state: dict) -> bool:
    def persist() -> None:
        with SessionLocal() as db:
            db.add(build_evaluation(ticket_id=ticket_id, run_id=run_id, state=state))
            db.commit()

    return try_persist_evaluation(persist)
