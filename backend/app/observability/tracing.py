"""供应商无关的 Trace 上下文和敏感字段脱敏。"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any


_SENSITIVE_KEYS = {"api_key", "authorization", "password", "token", "secret", "ocr_text", "raw_text", "image"}
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    ticket_id: int | str

    @classmethod
    def ensure(cls, trace_id: str | None, ticket_id: int | str) -> "TraceContext":
        candidate = trace_id or uuid.uuid4().hex
        if not _TRACE_ID_RE.fullmatch(candidate):
            raise ValueError("trace_id 格式无效")
        return cls(trace_id=candidate, ticket_id=ticket_id)


def sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """移除密钥、原始文本和文件内容，只保留可观测摘要。"""
    return {key: value for key, value in payload.items() if key.lower() not in _SENSITIVE_KEYS}

