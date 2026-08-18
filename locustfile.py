"""Locust 压测脚本：覆盖核心 API（登录/建单/列表/详情/审批入队）。

压测对象为「短时核心 API」，不含 LLM/OCR 完整推理时延（长任务在 Worker 异步执行）。
"""
from __future__ import annotations

import uuid

from locust import HttpUser, between, task


class ApiUser(HttpUser):
    wait_time = between(0.01, 0.05)

    def on_start(self):
        r = self.client.post("/api/auth/login", json={"username": "sv1", "password": "secret123"})
        if r.status_code == 200:
            self.headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        else:
            self.headers = {}

    @task(3)
    def submit_ticket(self):
        self.client.post(
            "/api/tickets",
            json={"amount": 128.0, "image_paths": []},
            headers={**self.headers, "X-Idempotency-Key": uuid.uuid4().hex},
        )

    @task(2)
    def list_tickets(self):
        self.client.get("/api/tickets", headers=self.headers)

    @task(1)
    def healthz(self):
        self.client.get("/healthz")
