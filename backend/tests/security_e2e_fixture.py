"""红蓝演练专用的 API→Worker 测试适配器，禁止被生产路由导入。"""
from __future__ import annotations

import os
import asyncio
from contextlib import nullcontext

import fakeredis
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("LLM_PROVIDER", "mock")

from app import models as _models  # noqa: E402,F401
from app.agents import nodes  # noqa: E402
from app.agents.ocr import OcrResult  # noqa: E402
from app.db import Base  # noqa: E402
from app.deps import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, Ticket, TicketStatus, User  # noqa: E402
from app.redis_client import get_redis  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.worker import consumer  # noqa: E402
class _FixtureOcr:
    def __init__(self, texts_by_path: dict[str, str]):
        self._texts_by_path = texts_by_path

    def extract(self, image_path: str) -> OcrResult:
        return OcrResult(self._texts_by_path[image_path], 0.95)


class _FixtureRisk:
    def score_fraud_with_usage(self, _material):
        from app.agents.llm import UsageSnapshot

        return 20, UsageSnapshot(1, 1, 2, "estimated")

    def classify_sentiment_with_usage(self, _material):
        from app.agents.llm import UsageSnapshot

        return "LOW", UsageSnapshot(1, 1, 2, "estimated")


class TestEnvironmentSubmitter:
    """以固定 OCR fixture 驱动真实 API 建单和 Worker 图更新。"""

    def __init__(self, cases: list[dict], outcome_factory):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self._Session = sessionmaker(bind=engine)
        self._redis = fakeredis.FakeRedis(decode_responses=True)
        self._texts = {f"fixture-{case['id']}.png": case["text"] for case in cases}
        self._outcome = outcome_factory
        self._worker_lock = asyncio.Lock()
        self._original = {
            "ocr": nodes._ocr_client,
            "risk": nodes._risk_client,
            "session": consumer.SessionLocal,
            "checkpointer": consumer.get_checkpointer,
            "evaluation": consumer.record_evaluation,
            "trace": consumer.emit_refund_trace,
            "event": consumer.publish_event,
        }
        nodes._ocr_client = _FixtureOcr(self._texts)
        nodes._risk_client = _FixtureRisk()
        consumer.SessionLocal = self._Session
        consumer.get_checkpointer = lambda: nullcontext(MemorySaver())
        consumer.record_evaluation = lambda **_kwargs: False
        consumer.emit_refund_trace = lambda **_kwargs: None
        consumer.publish_event = lambda *_args, **_kwargs: None

        def provide_db():
            db = self._Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = provide_db
        app.dependency_overrides[get_redis] = lambda: self._redis
        self._client = TestClient(app)
        self._client.__enter__()
        with self._Session() as db:
            user = User(username="security-e2e-runner", password_hash=hash_password("secret123"), role=Role.CS)
            db.add(user)
            db.commit()
        self._token = self._client.post(
            "/api/auth/login", json={"username": "security-e2e-runner", "password": "secret123"}
        ).json()["access_token"]

    async def __call__(self, case: dict):
        path = f"fixture-{case['id']}.png"
        response = self._client.post(
            "/api/tickets",
            json={"amount": 128, "image_paths": [path]},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        if response.status_code != 200:
            return self._outcome(str(case["id"]), False, "API_SUBMIT_FAILED", None)
        with self._Session() as db:
            ticket = db.get(Ticket, response.json()["ticket_id"])
            if ticket is None:
                return self._outcome(str(case["id"]), False, "TICKET_NOT_FOUND", None)
            ticket_id = ticket.id
            thread_id = ticket.thread_id
        async with self._worker_lock:
            await asyncio.to_thread(
                consumer.process, {"ticket_id": str(ticket_id), "thread_id": thread_id, "type": "START"}
            )
        with self._Session() as db:
            db.expire_all()
            persisted = db.get(Ticket, ticket_id)
            if persisted is None:
                return self._outcome(str(case["id"]), False, "WORKER_UPDATE_MISSING", None)
            route = "HUMAN_REVIEW" if persisted.status == TicketStatus.SUSPENDED else persisted.decision.value
            blocked = route == "HUMAN_REVIEW" and bool((persisted.evidence_audit or {}).get("security", {}).get("flags"))
            return self._outcome(str(case["id"]), blocked, None, route)

    def close(self) -> None:
        self._client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        nodes._ocr_client = self._original["ocr"]
        nodes._risk_client = self._original["risk"]
        consumer.SessionLocal = self._original["session"]
        consumer.get_checkpointer = self._original["checkpointer"]
        consumer.record_evaluation = self._original["evaluation"]
        consumer.emit_refund_trace = self._original["trace"]
        consumer.publish_event = self._original["event"]
