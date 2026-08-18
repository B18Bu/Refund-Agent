from app.models import Role, User
from app.security import hash_password


def _token(client, db_session, username, role):
    u = User(username=username, password_hash=hash_password("secret123"), role=role)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    r = client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    return r.json()["access_token"]


def test_create_ticket(client, db_session, redis_client):
    tok = _token(client, db_session, "cs1", Role.CS)
    r = client.post(
        "/api/tickets",
        json={"amount": 350.0, "image_paths": ["uploads/a.png"]},
        headers={"Authorization": f"Bearer {tok}", "X-Idempotency-Key": "k1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "RUNNING"
    assert body["outcome"] == "PENDING"
    # 已入队 START 消息
    msgs = redis_client.xrange("stream:tickets")
    assert len(msgs) == 1
    assert msgs[0][1]["type"] == "START"


def test_create_ticket_idempotent(client, db_session, redis_client):
    tok = _token(client, db_session, "cs1", Role.CS)
    h = {"Authorization": f"Bearer {tok}", "X-Idempotency-Key": "k2"}
    r1 = client.post("/api/tickets", json={"amount": 128.0}, headers=h)
    r2 = client.post("/api/tickets", json={"amount": 128.0}, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["ticket_id"] == r2.json()["ticket_id"]


def test_approve_requires_supervisor(client, db_session, redis_client):
    cs_tok = _token(client, db_session, "cs2", Role.CS)
    r = client.post(
        "/api/tickets/1/approve",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {cs_tok}"},
    )
    assert r.status_code == 403


def test_approve_not_suspended_conflict(client, db_session, redis_client):
    tok = _token(client, db_session, "sv1", Role.SV)
    r = client.post(
        "/api/tickets/999/approve",
        json={"action": "APPROVE"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    # 工单不存在 → 404；存在但非挂起 → 409
    assert r.status_code == 404


def test_list_tickets_requires_auth(client):
    assert client.get("/api/tickets").status_code == 401
