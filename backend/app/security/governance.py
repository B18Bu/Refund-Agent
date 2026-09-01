"""安全治理摘要：只聚合脱敏审计字段与结构化报告。"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import Ticket, TicketStatus


CURRENT_GAPS = [
    {
        "key": "action_policy",
        "title": "动作层统一治理",
        "description": "已拒绝工具和支付动作；未来显式能力仍需独立审批。",
        "status": "partial",
    },
    {
        "key": "ner_dlp",
        "title": "本地 NER 脱敏",
        "description": "正则 DLP 尚无 NER 验证集。",
        "status": "pending",
    },
    {
        "key": "red_blue_e2e",
        "title": "端到端红蓝演练",
        "description": "尚未覆盖 API 与 Worker 并发链路。",
        "status": "pending",
    },
    {
        "key": "llm_annotation",
        "title": "Critic 辅助注释",
        "description": "可选注释能力尚未落地。",
        "status": "pending",
    },
]

_SENSITIVE_KEY_PARTS = ("ocr", "raw", "token", "secret", "password", "api_key", "image")


def _safe_report(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _safe_report(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS)
        }
    if isinstance(value, list):
        return [_safe_report(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def read_report(path: Path) -> dict[str, Any]:
    """读取可选 JSON 报告；缺失、无效或非对象时显式不可用。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"available": False}
    if not isinstance(payload, dict):
        return {"available": False}
    return {"available": True, **_safe_report(payload)}


def _security_fields(ticket: Ticket) -> tuple[float, list[str]]:
    audit = ticket.evidence_audit if isinstance(ticket.evidence_audit, dict) else {}
    security = audit.get("security") if isinstance(audit.get("security"), dict) else {}
    raw_risk = security.get("risk", 0.0)
    try:
        risk = float(raw_risk)
    except (TypeError, ValueError):
        risk = 0.0
    if not math.isfinite(risk):
        risk = 0.0
    flags = security.get("flags", [])
    safe_flags = [str(flag) for flag in flags if isinstance(flag, str)] if isinstance(flags, list) else []
    return risk, sorted(set(safe_flags))


def _event_from_ticket(ticket: Ticket) -> dict[str, Any]:
    risk, flags = _security_fields(ticket)
    return {
        "ticket_ref": ticket.ticket_no,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "risk": risk,
        "flags": flags,
        "outcome": ticket.decision.value,
    }


def _has_security_event(ticket: Ticket) -> bool:
    _, flags = _security_fields(ticket)
    return bool(flags)


def build_summary(
    db: Session,
    *,
    red_blue_path: Path,
    dlp_path: Path,
    audit_path: Path,
) -> dict[str, Any]:
    """构造面向主管的只读治理摘要，绝不读取 OCR 或追踪原文。"""
    rows = db.query(Ticket).order_by(Ticket.created_at.desc()).limit(50).all()
    events = [_event_from_ticket(ticket) for ticket in rows if _has_security_event(ticket)]
    pending = sum(ticket.status == TicketStatus.SUSPENDED for ticket in rows)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runtime": {"pending_human_review": pending, "recent_events": events[:20]},
        "red_blue": read_report(red_blue_path),
        "dlp": read_report(dlp_path),
        "audit": read_report(audit_path),
        "gaps": [gap.copy() for gap in CURRENT_GAPS],
    }
