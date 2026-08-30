from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Decision, Role, Ticket, TicketStatus, User


def _create_ticket(db_session) -> Ticket:
    user = User(username="evaluation-owner", password_hash="not-used", role=Role.CS)
    db_session.add(user)
    db_session.flush()
    ticket = Ticket(
        ticket_no="evaluation-ticket-1",
        user_id=user.id,
        amount=128,
        image_paths=[],
        status=TicketStatus.COMPLETED,
        decision=Decision.AUTO_REFUNDED,
    )
    db_session.add(ticket)
    db_session.commit()
    return ticket


def test_evaluation_run_is_unique_and_related_to_ticket(db_session):
    from app.evaluation.models import AgentEvaluationRun

    ticket = _create_ticket(db_session)
    first = AgentEvaluationRun(
        ticket_id=ticket.id,
        run_id="thread-1:start",
        prompt_version="refund-v2",
        provider="mock",
        measurement_type="estimated",
        evaluation_status="PASSED",
    )
    db_session.add(first)
    db_session.commit()

    assert first.ticket.id == ticket.id
    assert ticket.evaluations == [first]

    db_session.add(
        AgentEvaluationRun(
            ticket_id=ticket.id,
            run_id="thread-1:start",
            prompt_version="refund-v2",
            provider="mock",
            measurement_type="estimated",
            evaluation_status="PASSED",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_evaluation_run_keeps_only_auditable_metrics():
    from app.evaluation.models import AgentEvaluationRun

    columns = set(AgentEvaluationRun.__table__.columns.keys())
    assert {
        "baseline_input_tokens",
        "current_input_tokens",
        "current_output_tokens",
        "current_total_tokens",
        "saved_tokens",
        "reduction_ratio",
        "correctness_score",
        "safety_score",
        "explainability_score",
        "latency_breakdown",
        "decision_route",
        "reason_summary",
        "error_code",
    } <= columns
    assert {"prompt", "api_key", "raw_image", "ocr_text"}.isdisjoint(columns)


def test_explicit_migration_matches_model_columns():
    from app.evaluation.models import AgentEvaluationRun

    migration_path = (
        Path(__file__).parents[1]
        / "migrations"
        / "20260830_add_agent_evaluation_runs.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()
    assert "create table if not exists agent_evaluation_runs" in sql
    assert "create unique index if not exists" in sql
    assert "create index if not exists" in sql
    for column in AgentEvaluationRun.__table__.columns.keys():
        assert column.lower() in sql
