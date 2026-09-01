from app.models import Decision, Role, Ticket, TicketStatus, User
from app.security import hash_password


def _token(client, db_session, username: str, role: Role) -> str:
    db_session.add(User(username=username, password_hash=hash_password("secret123"), role=role))
    db_session.commit()
    response = client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    return response.json()["access_token"]


def test_security_governance_summary_requires_supervisor(client, db_session):
    customer_token = _token(client, db_session, "governance-cs", Role.CS)

    response = client.get(
        "/api/security-governance/summary",
        headers={"Authorization": f"Bearer {customer_token}"},
    )

    assert response.status_code == 403


def test_supervisor_summary_never_exposes_ocr_text(client, db_session):
    supervisor_token = _token(client, db_session, "governance-sv", Role.SV)
    supervisor = db_session.query(User).filter(User.username == "governance-sv").one()
    db_session.add(
        Ticket(
            ticket_no="governance-api-ticket",
            user_id=supervisor.id,
            amount=128,
            image_paths=[],
            status=TicketStatus.SUSPENDED,
            decision=Decision.PENDING,
            evidence_audit={"security": {"risk": 1.0, "flags": ["dangerous_tool"]}},
            ocr_text="13812340000 sk-secret-never-return",
        )
    )
    db_session.commit()

    response = client.get(
        "/api/security-governance/summary",
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )

    assert response.status_code == 200
    assert response.json()["runtime"]["recent_events"][0]["flags"] == ["dangerous_tool"]
    assert "13812340000" not in str(response.json())
    assert "sk-secret-never-return" not in str(response.json())
