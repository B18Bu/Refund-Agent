"""Worker 消费者：Redis Streams 消费 + LangGraph Redis Checkpointer 执行决策流。

三方对齐消息一致性（A-03，P0）：
- 成功处理 → XACK。
- 不可恢复异常 → 先落库 `COMPLETED + FAILED + error_code + error_message`，再 XACK。
- checkpoint 缺失（A-07）→ `FAILED + CHECKPOINT_NOT_FOUND`。
- 挂起（interrupt）→ 状态置 SUSPENDED，消息正常 XACK（决策流已在人工节点等待恢复）。
"""
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from langgraph.types import Command
from sqlalchemy.orm import Session

from app.agents.checkpointer import get_checkpointer
from app.agents.graph import build_graph
from app.config import settings
from app.db import SessionLocal
from app.evaluation.repository import record_evaluation, should_record_evaluation
from app.models import AgentTrace, Decision, Ticket, TicketStatus
from app.observability.langfuse import emit_refund_trace
from app.redis_client import get_redis
from app.security.gateway import DLP

logger = logging.getLogger("worker")


# ============ 错误码（三方对齐 A-07 / specs 错误语义表） ============
ERR_CHECKPOINT_NOT_FOUND = "CHECKPOINT_NOT_FOUND"
ERR_PROCESS_FAILED = "PROCESS_FAILED"


def update_ticket(thread_id: str, **fields) -> None:
    with SessionLocal() as db:
        t = db.query(Ticket).filter(Ticket.thread_id == thread_id).first()
        if t:
            for k, v in fields.items():
                setattr(t, k, v)
            db.commit()


def find_ticket_by_thread(thread_id: str):
    with SessionLocal() as db:
        return db.query(Ticket).filter(Ticket.thread_id == thread_id).first()


def mark_failed(ticket_id: int, error_code: str, error_message: str) -> None:
    """不可恢复错误：落库 COMPLETED + FAILED + error_code，再 XACK。"""
    with SessionLocal() as db:
        t = db.get(Ticket, ticket_id)
        if t is None:
            logger.error("mark_failed: 工单 %s 不存在", ticket_id)
            return
        t.status = TicketStatus.COMPLETED
        t.decision = Decision.FAILED
        t.error_code = error_code
        t.error_message = error_message[:2000]
        t.completed_at = datetime.now(timezone.utc)
        db.commit()
        trace_failed(db, t.id, "Worker", error_code, error_message)


def trace_failed(db: Session, ticket_id: int, agent_name: str, error_code: str, msg: str) -> None:
    seq = db.query(AgentTrace).filter(AgentTrace.ticket_id == ticket_id).count() + 1
    db.add(AgentTrace(
        ticket_id=ticket_id,
        sequence_no=seq,
        agent_name=agent_name,
        status="FAILED",
        output_summary=msg,
        error_code=error_code,
        ended_at=datetime.now(timezone.utc),
    ))
    db.commit()


def run_once() -> int:
    """消费一批消息。返回处理条数。"""
    redis = get_redis()
    try:
        redis.xgroup_create(settings.STREAM_KEY, settings.CONSUMER_GROUP, id="0", mkstream=True)
    except Exception:
        pass

    msgs = redis.xreadgroup(
        settings.CONSUMER_GROUP,
        settings.CONSUMER_NAME,
        {settings.STREAM_KEY: ">"},
        count=1,
        block=5000,
    )
    if not msgs:
        return 0

    processed = 0
    for _stream, entries in msgs:
        for msg_id, fields in entries:
            processed += 1
            try:
                process(fields)
                redis.xack(settings.STREAM_KEY, settings.CONSUMER_GROUP, msg_id)
            except Exception as e:
                logger.exception("process error: %s", e)
                # A-03：不可恢复异常 → 先落 FAILED，再 XACK（保证不丢消息且状态可审计）
                trace_id = fields.get("trace_id") or uuid.uuid4().hex
                emit_refund_trace(
                    trace_id=trace_id,
                    ticket_id=int(fields["ticket_id"]),
                    spans=[],
                    error_code=ERR_PROCESS_FAILED,
                )
                try:
                    # 工单 8：失败消息进死信队列（含原因、trace_id、重试计数），与原落库并存
                    redis.xadd(
                        settings.DLQ_STREAM_KEY,
                        {
                            "ticket_id": fields.get("ticket_id", ""),
                            "thread_id": fields.get("thread_id", ""),
                            "trace_id": trace_id,
                            "error_code": ERR_PROCESS_FAILED,
                            "error_message": f"Worker 处理异常: {e}"[:2000],
                            "retry_count": "0",
                            "ts": datetime.now(timezone.utc).isoformat(),
                        },
                        maxlen=1000,
                    )
                except Exception as e2:
                    logger.error("DLQ 写入失败: %s", e2)
                try:
                    mark_failed(int(fields["ticket_id"]), ERR_PROCESS_FAILED, f"Worker 处理异常: {e}")
                except Exception as e2:
                    logger.error("mark_failed 失败: %s", e2)
                redis.xack(settings.STREAM_KEY, settings.CONSUMER_GROUP, msg_id)
    return processed


# 节点名 → 展示名（与大屏 FlowCanvas 顺序一致）
_NODE_DISPLAY = {
    "intake": "Intake",
    "ocr": "OCR",
    "critic": "Security",
    "intent": "Intent",
    "risk": "Risk",
    "fallback": "Fallback",
    "decision": "Decision",
    "human_review": "HumanReview",
}


def write_trace(ticket_id: int, agent_name: str, status: str, output_summary: str | None = None,
                error_code: str | None = None) -> None:
    with SessionLocal() as db:
        seq = db.query(AgentTrace).filter(AgentTrace.ticket_id == ticket_id).count() + 1
        db.add(AgentTrace(
            ticket_id=ticket_id,
            sequence_no=seq,
            agent_name=agent_name,
            status=status,
            output_summary=output_summary,
            error_code=error_code,
            ended_at=datetime.now(timezone.utc),
        ))
        db.commit()


def publish_event(ticket_id: int, event: str, payload: dict) -> None:
    try:
        redis = get_redis()
        data = json.dumps({"event": event, "ticket_id": ticket_id, **payload}, ensure_ascii=False)
        redis.publish(f"{settings.EVENT_CHANNEL_PREFIX}:{ticket_id}", data)
    except Exception as exc:
        logger.warning("publish_event 失败: %s", exc)


def process(fields: dict) -> None:
    ticket_id = int(fields["ticket_id"])
    thread_id = fields["thread_id"]
    trace_id = fields.get("trace_id") or uuid.uuid4().hex
    msg_type = fields.get("type", "START")
    resume_action = fields.get("resume_action")
    is_resume = msg_type.upper() == "RESUME" or bool(resume_action)
    spans: list[dict] = []

    with get_checkpointer() as checkpointer:
        graph = build_graph().compile(checkpointer=checkpointer)
        cfg = {"configurable": {"thread_id": thread_id}}

        if is_resume:
            # A-07：checkpoint 缺失兜底（恢复时若无已保存的图状态 → FAILED + CHECKPOINT_NOT_FOUND）
            snap0 = graph.get_state(cfg)
            if not snap0 or not snap0.values:
                raise CheckpointNotFound(f"thread={thread_id} checkpoint 缺失")
            update_ticket(thread_id, status=TicketStatus.RUNNING)
            publish_event(ticket_id, "ticket_status_changed", {"status": "RUNNING", "outcome": "PENDING"})
            # stream 模式捕获 human_review 节点输出（approval_action 落库轨迹）
            for _ in graph.stream(Command(resume={"action": resume_action}), config=cfg, stream_mode="updates"):
                pass
            spans.append({"name": "HumanReview", "status": "SUCCESS", "output": {"action": resume_action}})
        else:
            with SessionLocal() as db:
                t = db.get(Ticket, ticket_id)
                if t is None:
                    raise TicketNotFound(f"工单 {ticket_id} 不存在")
                initial = {
                    "ticket_id": str(ticket_id),
                    "trace_id": trace_id,
                    "amount": float(t.amount),
                    "image_paths": t.image_paths or [],
                }
            update_ticket(thread_id, status=TicketStatus.RUNNING, trace_id=trace_id)
            # stream 遇 interrupt 不抛异常；updates 模式逐节点回调写轨迹
            for chunk in graph.stream(initial, config=cfg, stream_mode="updates"):
                for node_name, node_out in (chunk or {}).items():
                    if node_name == "__interrupt__":
                        continue
                    display = _NODE_DISPLAY.get(node_name, node_name.title())
                    status = "SUSPENDED" if node_name == "human_review" else "SUCCESS"
                    summary = None
                    if node_name == "ocr":
                        summary = DLP.mask(node_out.get("ocr_text", ""))[0]
                    elif node_name == "critic":
                        summary = (
                            f"risk={node_out.get('critic_risk')} "
                            f"flags={','.join(node_out.get('security_flags', []))}"
                        )
                    elif node_name == "intent":
                        summary = (
                            f"route={node_out.get('intent_route')} "
                            f"label={node_out.get('intent_label')} "
                            f"rules={','.join(node_out.get('intent_hit_rules', []))}"
                        )
                    elif node_name == "risk":
                        summary = (
                            f"fraud_score={node_out.get('fraud_score')} "
                            f"sentiment={node_out.get('sentiment')} "
                            f"parallel_ms={node_out.get('latency_breakdown', {}).get('risk_parallel_ms')}"
                        )
                    elif node_name == "fallback":
                        summary = f"fallback={','.join(node_out.get('fallback_reasons', [])) or 'none'}"
                    elif node_name == "decision":
                        summary = f"{node_out.get('decision', '')}: {','.join(node_out.get('decision_reasons', []))}"
                        if node_out.get("management_suggestion"):
                            summary += f" | 建议：{node_out['management_suggestion']}"
                    write_trace(ticket_id, display, status, summary)
                    spans.append({"name": display, "status": status, "output": {"summary": summary}})
                    publish_event(ticket_id, "trace_updated", {"agent_name": display, "status": status})

        # 判断是否挂起（interrupt 在 human_review 节点）
        snapshot = graph.get_state(cfg)
        state = snapshot.values or {}
        trace_id = state.get("trace_id") or trace_id
        if should_record_evaluation("RESUME" if is_resume else msg_type):
            record_evaluation(
                ticket_id=ticket_id,
                run_id=f"{thread_id}:start",
                state=state,
            )
        if snapshot.next and "human_review" in snapshot.next:
            # 挂起时也保存 OCR/风控/舆情中间结果，供主管审批前查看证据
            update_ticket(
                thread_id,
                status=TicketStatus.SUSPENDED,
                ocr_text=state.get("ocr_text"),
                ocr_confidence=state.get("ocr_confidence"),
                fraud_score=state.get("fraud_score"),
                sentiment=state.get("sentiment"),
                decision_reasons=state.get("decision_reasons"),
                evidence_audit=state.get("evidence_audit"),
                management_suggestion=state.get("management_suggestion"),
            )
            publish_event(ticket_id, "ticket_status_changed", {"status": "SUSPENDED", "outcome": "PENDING"})
            emit_refund_trace(trace_id=trace_id, ticket_id=ticket_id, spans=spans, final_decision="PENDING")
            return

        # 未挂起 → 读取最终 state 落库
        final_decision = state.get("final_decision", "REJECTED")
        if final_decision not in ("AUTO_REFUNDED", "APPROVED", "REJECTED"):
            final_decision = "REJECTED"
        update_ticket(
            thread_id,
            status=TicketStatus.COMPLETED,
            decision=Decision(final_decision),
            ocr_text=state.get("ocr_text"),
            ocr_confidence=state.get("ocr_confidence"),
            fraud_score=state.get("fraud_score"),
            sentiment=state.get("sentiment"),
            decision_reasons=state.get("decision_reasons"),
            evidence_audit=state.get("evidence_audit"),
            management_suggestion=state.get("management_suggestion"),
            completed_at=datetime.now(timezone.utc),
        )
        publish_event(ticket_id, "completed", {"outcome": final_decision})
        emit_refund_trace(trace_id=trace_id, ticket_id=ticket_id, spans=spans, final_decision=final_decision)


class CheckpointNotFound(Exception):
    pass


class TicketNotFound(Exception):
    pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger.info("worker started")
    while True:
        run_once()
        time.sleep(0.05)
