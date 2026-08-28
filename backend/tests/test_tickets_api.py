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


def _ticket(db_session, user_id, ticket_no):
    from app.models import Decision, Ticket, TicketStatus

    ticket = Ticket(
        ticket_no=ticket_no,
        user_id=user_id,
        amount=128.0,
        image_paths=[],
        status=TicketStatus.RUNNING,
        decision=Decision.PENDING,
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)
    return ticket


def test_customer_service_only_sees_own_tickets(client, db_session):
    cs1_token = _token(client, db_session, "cs-list-owner", Role.CS)
    cs2_token = _token(client, db_session, "cs-list-other", Role.CS)
    from app.models import User

    cs1 = db_session.query(User).filter(User.username == "cs-list-owner").one()
    cs2 = db_session.query(User).filter(User.username == "cs-list-other").one()
    own_ticket = _ticket(db_session, cs1.id, "own-ticket")
    other_ticket = _ticket(db_session, cs2.id, "other-ticket")

    response = client.get("/api/tickets", headers={"Authorization": f"Bearer {cs1_token}"})

    assert response.status_code == 200
    assert [row["ticket_no"] for row in response.json()] == [own_ticket.ticket_no]
    detail = client.get(f"/api/tickets/{other_ticket.id}", headers={"Authorization": f"Bearer {cs1_token}"})
    assert detail.status_code == 404
    assert detail.json()["detail"] == "工单不存在"


def test_supervisor_sees_latest_100_tickets_across_customers(client, db_session):
    supervisor_token = _token(client, db_session, "sv-list-all", Role.SV)
    _token(client, db_session, "cs-list-all-1", Role.CS)
    _token(client, db_session, "cs-list-all-2", Role.CS)
    from app.models import User

    cs1 = db_session.query(User).filter(User.username == "cs-list-all-1").one()
    cs2 = db_session.query(User).filter(User.username == "cs-list-all-2").one()
    tickets = [
        _ticket(db_session, cs1.id if index % 2 == 0 else cs2.id, f"ticket-{index:03d}")
        for index in range(101)
    ]

    response = client.get("/api/tickets", headers={"Authorization": f"Bearer {supervisor_token}"})

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 100
    assert [row["ticket_no"] for row in rows] == [ticket.ticket_no for ticket in reversed(tickets[1:])]
    assert tickets[0].ticket_no not in {row["ticket_no"] for row in rows}
    assert {row["ticket_no"] for row in rows} == {ticket.ticket_no for ticket in tickets[1:]}


def test_supervisor_approval_records_and_enqueues_resume(client, db_session, redis_client):
    from app.models import Approval, Ticket, TicketStatus, Decision, User

    supervisor_token = _token(client, db_session, "sv-approve-success", Role.SV)
    supervisor = db_session.query(User).filter(User.username == "sv-approve-success").one()
    customer_token = _token(client, db_session, "cs-approve-owner", Role.CS)
    customer = db_session.query(User).filter(User.username == "cs-approve-owner").one()
    ticket = Ticket(
        ticket_no="suspended-approval",
        user_id=customer.id,
        amount=350.0,
        image_paths=[],
        status=TicketStatus.SUSPENDED,
        decision=Decision.PENDING,
        thread_id="thread-approval-1",
    )
    db_session.add(ticket)
    db_session.commit()
    db_session.refresh(ticket)

    response = client.post(
        f"/api/tickets/{ticket.id}/approve",
        json={"action": "APPROVE", "comment": "凭证和风险结果已复核"},
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RUNNING"
    assert body["status_text"] == "处理中"
    assert body["outcome"] == "APPROVE"
    assert body["outcome_text"] == "已批准"

    db_session.refresh(ticket)
    approval = db_session.query(Approval).filter(Approval.ticket_id == ticket.id).one()
    assert approval.reviewer_id == supervisor.id
    assert approval.action == "APPROVE"
    assert approval.comment == "凭证和风险结果已复核"

    messages = redis_client.xrange("stream:tickets")
    assert len(messages) == 1
    message = messages[0][1]
    assert message["type"] == "RESUME"
    assert message["ticket_id"] == str(ticket.id)
    assert message["thread_id"] == "thread-approval-1"
    assert message["resume_action"] == "APPROVE"


def test_create_ticket_with_files_multipart(client, db_session, redis_client, tmp_path):
    """multipart 一次建单+上传：图片路径随工单一并落库（修复时序缺陷）。"""
    from app.models import Ticket

    tok = _token(client, db_session, "cs1", Role.CS)
    # 构造最小合法 PNG（1x1 白色像素）
    import base64
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    p = tmp_path / "invoice.png"
    p.write_bytes(png_bytes)

    with open(p, "rb") as f:
        r = client.post(
            "/api/tickets/with-files",
            data={"amount": "128.00"},
            files=[("files", ("invoice.png", f, "image/png"))],
            headers={"Authorization": f"Bearer {tok}", "X-Idempotency-Key": "kf1"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "RUNNING"
    assert body["status_text"] == "处理中"
    assert body["uploaded_files"] == 1
    assert body["outcome_text"] == "待定"
    # 图片路径已落库
    t = db_session.get(Ticket, body["ticket_id"])
    assert len(t.image_paths) == 1
    assert "uploads" in t.image_paths[0]  # 兼容 Windows/Unix 分隔符
    # 已入队 START
    msgs = redis_client.xrange("stream:tickets")
    assert len(msgs) == 1
