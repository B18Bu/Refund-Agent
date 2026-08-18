import os

# 必须在导入 app.main 之前设置：testing 环境跳过 lifespan 的 postgres 建表/种子
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("LLM_PROVIDER", "mock")

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def client(db_engine, redis_client):
    # 延迟导入：app.deps / app.main 在任务 6 才存在
    from app.deps import get_db
    from app.redis_client import get_redis
    from app.main import app

    Session = sessionmaker(bind=db_engine)

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_redis] = lambda: redis_client
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
