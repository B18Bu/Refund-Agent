"""Langfuse 公共 API 适配器（ingestion 批量上报，无 OTel/protobuf 依赖）。

选型说明：Langfuse Python SDK 依赖 opentelemetry/protobuf >=5，
与本项目 Windows 本地 PaddleOCR 所需的 protobuf<=3.20.2 冲突；
因此改用 Langfuse 公共 ingestion API（`POST /api/public/ingestion`，Basic 认证公钥/私钥），
既避免依赖冲突，又满足 AGENTS.md 约束：

- Telemetry 不阻塞业务主流程：经有界后台队列异步发送，队列满只计数丢观测；
- 不改变审批结果：任何上报异常仅记录日志；
- 只上报脱敏摘要：原始 OCR 文本、密钥、文件内容一律剔除。
"""
from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.observability.queue import TelemetryQueue
from app.observability.tracing import sanitize_payload

logger = logging.getLogger(__name__)

_queue: TelemetryQueue | None = None


def telemetry_enabled() -> bool:
    return bool(
        settings.TELEMETRY_ENABLED
        and settings.TELEMETRY_PROVIDER == "langfuse"
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
    )


def _sanitize(value: Any) -> Any:
    return sanitize_payload(value) if isinstance(value, dict) else value


def _auth_headers() -> dict[str, str]:
    token = base64.b64encode(
        f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}".encode()
    ).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def _post(payload: dict[str, Any]) -> None:
    host = (settings.LANGFUSE_BASE_URL or settings.LANGFUSE_HOST).rstrip("/")
    resp = httpx.post(
        f"{host}/api/public/ingestion",
        headers=_auth_headers(),
        json=payload,
        timeout=5.0,
    )
    resp.raise_for_status()


def get_queue() -> TelemetryQueue:
    """全局有界后台队列；队列满时丢弃观测并计数，不阻塞业务。"""
    global _queue
    if _queue is None:
        _queue = TelemetryQueue(maxsize=1000, exporter=_post)
    return _queue


def emit_refund_trace(
    *,
    trace_id: str,
    ticket_id: int | str,
    spans: list[dict],
    final_decision: str | None = None,
    error_code: str | None = None,
) -> bool:
    """上报一次退赔决策 Trace（含各节点脱敏 span）。返回是否已入队。"""
    if not telemetry_enabled():
        return False
    now = datetime.now(timezone.utc).isoformat()
    batch = [
        {
            "id": uuid.uuid4().hex,
            "type": "trace-create",
            "timestamp": now,
            "body": {
                "id": trace_id,
                "name": "refund_decision",
                "metadata": {"ticket_id": str(ticket_id)},
                "timestamp": now,
            },
        }
    ]
    output: dict[str, Any] | None = None
    if final_decision or error_code:
        output = {"final_decision": final_decision, "error_code": error_code}
    for span in spans:
        batch.append(
            {
                "id": uuid.uuid4().hex,
                "type": "span-create",
                "timestamp": now,
                "body": {
                    "id": uuid.uuid4().hex,
                    "traceId": trace_id,
                    "name": span.get("name", "step"),
                    "startTime": now,
                    "endTime": now,
                    "input": _sanitize(span.get("input")),
                    "output": _sanitize(span.get("output")),
                    "metadata": {"status": span.get("status", "SUCCESS")},
                    "level": "ERROR" if span.get("status") not in (None, "SUCCESS") else "DEFAULT",
                },
            }
        )
    payload = {"batch": batch}
    return get_queue().emit(payload)


def shutdown(timeout: float = 2.0) -> None:
    """停止后台发送线程（进程退出前调用）。"""
    global _queue
    if _queue is not None:
        _queue.close(timeout=timeout)
        _queue = None
