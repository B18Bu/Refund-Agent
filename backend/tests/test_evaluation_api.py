from app.evaluation.models import AgentEvaluationRun
from app.models import Decision, Role, Ticket, TicketStatus, User
from app.security import hash_password


def _login(client, db_session, username, role):
    user = User(username=username, password_hash=hash_password("secret123"), role=role)
    db_session.add(user)
    db_session.commit()
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "secret123"},
    )
    return response.json()["access_token"], user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _ticket(db_session, user_id):
    ticket = Ticket(
        ticket_no="evaluation-api-ticket",
        user_id=user_id,
        amount=128,
        image_paths=[],
        status=TicketStatus.COMPLETED,
        decision=Decision.AUTO_REFUNDED,
    )
    db_session.add(ticket)
    db_session.commit()
    return ticket


def test_customer_service_cannot_read_evaluations(client, db_session):
    token, _ = _login(client, db_session, "cs-eval", Role.CS)

    assert client.get("/api/evaluations/summary", headers=_auth(token)).status_code == 403


def test_supervisor_gets_empty_summary_without_fake_points(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "GOLDEN_REPORT_PATH", "missing-golden-report.json", raising=False)
    token, _ = _login(client, db_session, "sv-eval-empty", Role.SV)

    response = client.get("/api/evaluations/summary", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_count"] == 0
    assert body["trend"] == []
    assert body["recent"] == []
    assert body["golden"] == {"available": False}


def test_missing_ticket_evaluation_is_an_explicit_empty_state(client, db_session):
    token, _ = _login(client, db_session, "sv-eval-missing", Role.SV)

    response = client.get("/api/tickets/999/evaluation", headers=_auth(token))

    assert response.status_code == 200
    assert response.json() == {"available": False, "status": "NOT_AVAILABLE"}


def test_summary_and_detail_use_persisted_values(client, db_session, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "GOLDEN_REPORT_PATH", "missing-golden-report.json", raising=False)
    token, supervisor = _login(client, db_session, "sv-eval-values", Role.SV)
    ticket = _ticket(db_session, supervisor.id)
    db_session.add(
        AgentEvaluationRun(
            ticket_id=ticket.id,
            run_id="evaluation-api:start",
            prompt_version="refund-v1",
            provider="mock",
            measurement_type="estimated",
            baseline_input_tokens=100,
            current_input_tokens=60,
            current_output_tokens=10,
            current_total_tokens=70,
            saved_tokens=40,
            reduction_ratio=0.4,
            correctness_score=2,
            safety_score=2,
            explainability_score=2,
            evaluation_status="PASSED",
            latency_breakdown={"fraud_ms": 4.2},
            decision_route="AUTO_REFUND",
            reason_summary="amount_within_limit,fraud_pass",
        )
    )
    db_session.commit()

    summary = client.get("/api/evaluations/summary", headers=_auth(token)).json()
    detail = client.get(f"/api/tickets/{ticket.id}/evaluation", headers=_auth(token)).json()

    assert summary["evaluation_count"] == 1
    assert summary["avg_baseline_input_tokens"] == 100
    assert summary["avg_current_input_tokens"] == 60
    assert summary["avg_saved_tokens"] == 40
    assert summary["avg_reduction_ratio"] == 0.4
    assert len(summary["trend"]) == 1
    assert detail["available"] is True
    assert detail["record"]["measurement_type"] == "estimated"
    assert detail["record"]["current_total_tokens"] == 70


def test_application_startup_does_not_silently_create_evaluation_table(monkeypatch):
    from app import main

    calls = []
    monkeypatch.setattr(
        main.Base.metadata,
        "create_all",
        lambda **kwargs: calls.append(kwargs),
    )

    main.init_db()

    table_names = {table.name for table in calls[0]["tables"]}
    assert "tickets" in table_names
    assert "agent_evaluation_runs" not in table_names
