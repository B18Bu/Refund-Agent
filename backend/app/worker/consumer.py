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
from datetime import datetime, timezone

from langgraph.checkpoint.redis import RedisSaver
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.agents.graph import build_graph
from app.config import settings
from app.db import SessionLocal
from app.models import AgentTrace, Decision, Ticket, TicketStatus
from app.redis_client import get_redis

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
                try:
                    mark_failed(int(fields["ticket_id"]), ERR_PROCESS_FAILED, f"Worker 处理异常: {e}")
                except Exception as e2:
                    logger.error("mark_failed 失败: %s", e2)
                redis.xack(settings.STREAM_KEY, settings.CONSUMER_GROUP, msg_id)
    return processed


def process(fields: dict) -> None:
    ticket_id = int(fields["ticket_id"])
    thread_id = fields["thread_id"]
    msg_type = fields.get("type", "START")
    resume_action = fields.get("resume_action")

    with RedisSaver.from_conn_string(settings.REDIS_URL) as checkpointer:
        graph = build_graph().compile(checkpointer=checkpointer)
        cfg = {"configurable": {"thread_id": thread_id}}

        if msg_type == "RESUME" or resume_action:
            # A-07：checkpoint 缺失兜底
            snap0 = graph.get_state(cfg)
            if not snap0 or snap0.next is None and not snap0.values:
                raise CheckpointNotFound(f"thread={thread_id} checkpoint 缺失")
            update_ticket(thread_id, status=TicketStatus.RUNNING)
            graph.invoke(Command(resume={"action": resume_action}), config=cfg)
        else:
            with SessionLocal() as db:
                t = db.get(Ticket, ticket_id)
                if t is None:
                    raise TicketNotFound(f"工单 {ticket_id} 不存在")
                initial = {
                    "ticket_id": str(ticket_id),
                    "amount": float(t.amount),
                    "image_paths": t.image_paths or [],
                }
            update_ticket(thread_id, status=TicketStatus.RUNNING)
            for _ in graph.stream(initial, config=cfg):
                pass  # stream 遇 interrupt 不抛异常，挂起判定见下

        # 判断是否挂起（interrupt 在 human_review 节点）
        snapshot = graph.get_state(cfg)
        if snapshot.next and "human_review" in snapshot.next:
            update_ticket(thread_id, status=TicketStatus.SUSPENDED)
            return

        # 未挂起 → 读取最终 state 落库
        state = snapshot.values or {}
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
            completed_at=datetime.now(timezone.utc),
        )


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
