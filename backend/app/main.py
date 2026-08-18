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
    """幂等创建演示用户（兼容两套命名，密码统一 secret123）。

    - cs1 / sv1：实现计划（人工方）命名
    - customer_service_01 / supervisor_01：specs / quickstart（AI-B 规范）命名
    """
    demo_users = [
        ("cs1", Role.CS),
        ("sv1", Role.SV),
        ("customer_service_01", Role.CS),
        ("supervisor_01", Role.SV),
    ]
    with SessionLocal() as db:
        for username, role in demo_users:
            if db.query(User).filter(User.username == username).first() is None:
                db.add(User(username=username, password_hash=hash_password("secret123"), role=role))
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
