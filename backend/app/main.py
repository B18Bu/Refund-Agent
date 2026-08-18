"""FastAPI 入口：挂路由 + 启动建表 + 种子用户 + 健康检查。"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.db import Base, engine, SessionLocal
from app.models import Role, User
from app.routers import auth, files, tickets
from app.security import hash_password


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def seed_users() -> None:
    """幂等创建演示用户：cs1（客服）/ sv1（主管）。"""
    with SessionLocal() as db:
        if db.query(User).filter(User.username == "cs1").first() is None:
            db.add(User(username="cs1", password_hash=hash_password("secret123"), role=Role.CS))
        if db.query(User).filter(User.username == "sv1").first() is None:
            db.add(User(username="sv1", password_hash=hash_password("secret123"), role=Role.SV))
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("ENVIRONMENT", "development") != "testing":
        init_db()
        seed_users()
    yield


app = FastAPI(title="客诉舆情退赔决策系统", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(files.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        return {"status": "not_ready", "detail": str(exc)}, 503
    return {"status": "ready"}
