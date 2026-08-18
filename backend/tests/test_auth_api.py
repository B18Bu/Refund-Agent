from app.models import Role, User
from app.security import hash_password


def _make_user(db, username, role):
    u = User(username=username, password_hash=hash_password("secret123"), role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_login_success(client, db_session):
    _make_user(db_session, "sv1", Role.SV)
    r = client.post("/api/auth/login", json={"username": "sv1", "password": "secret123"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["expires_in"] == 7200


def test_login_wrong_password(client, db_session):
    _make_user(db_session, "sv1", Role.SV)
    r = client.post("/api/auth/login", json={"username": "sv1", "password": "bad"})
    assert r.status_code == 401


def test_login_unknown_user(client):
    r = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


def test_healthz(client):
    assert client.get("/healthz").status_code == 200
