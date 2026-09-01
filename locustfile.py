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

    @task(1)
    def submit_ticket(self):
        self.client.post(
            "/api/tickets",
            json={"amount": 128.0, "image_paths": []},
            headers={**self.headers, "X-Idempotency-Key": uuid.uuid4().hex},
        )

    @task(3)
    def list_tickets(self):
        self.client.get("/api/tickets", headers=self.headers)

    @task(2)
    def view_ticket_detail(self):
        resp = self.client.get("/api/tickets", headers=self.headers)
        if resp.status_code == 200 and resp.json():
            self.client.get(f"/api/tickets/{resp.json()[0]['id']}", headers=self.headers)

    @task(1)
    def approve_suspended(self):
        resp = self.client.get("/api/tickets", headers=self.headers)
        if resp.status_code == 200:
            for ticket in resp.json():
                if ticket.get("status") == "SUSPENDED":
                    with self.client.post(
                        f"/api/tickets/{ticket['id']}/approve",
                        json={"action": "APPROVE", "comment": "locust"},
                        headers=self.headers,
                        catch_response=True,
                    ) as r:
                        # 409 是“已审批/非挂起”的业务预期冲突，不是系统故障
                        if r.status_code == 409:
                            r.success()
                    break

    @task(1)
    def healthz(self):
        self.client.get("/healthz")
