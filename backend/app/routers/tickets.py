"""工单路由：创建/列表/详情/审批 + SSE 事件流。

审批采用「入队 RESUME 消息由 Worker 串行 resume」方式（三方对齐：API 不直接 resume LangGraph）。
"""
import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.deps import get_current_user, get_db, require_role
from app.idempotency import resolve_idempotency
from app.locks import acquire_approve_lock, release_approve_lock
from app.models import Approval, Decision, Role, Ticket, TicketStatus
from app.redis_client import get_redis
from app.schemas import ApproveRequest, ApproveResponse, TicketCreate

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.post("")
def create_ticket(
    body: TicketCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
    x_idempotency_key: str | None = Header(None),
):
    idem_key = x_idempotency_key or uuid.uuid4().hex
    ticket_no = uuid.uuid4().hex
    redis_key = f"idem:{user.id}:{idem_key}"
    existing = resolve_idempotency(redis, redis_key, str(ticket_no))  # SET NX，值=ticket_no
    if existing is not None:
        # 幂等命中：返回首次创建的工单
        ticket = db.query(Ticket).filter(Ticket.ticket_no == existing).first()
        if ticket:
            return {
                "ticket_id": ticket.id,
                "ticket_no": ticket.ticket_no,
                "status": ticket.status.value,
                "outcome": ticket.decision.value,
            }

    ticket = Ticket(
        ticket_no=ticket_no,
        user_id=user.id,
        amount=body.amount,
        image_paths=body.image_paths,
        status=TicketStatus.RUNNING,
        decision=Decision.PENDING,
        thread_id=uuid.uuid4().hex,
        idempotency_key=idem_key,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    # 写入 Streams 交给 Worker（START 消息）
    redis.xadd(
        settings.STREAM_KEY,
        {"type": "START", "ticket_id": str(ticket.id), "thread_id": ticket.thread_id},
    )
    return {
        "ticket_id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "status": ticket.status.value,
        "outcome": ticket.decision.value,
    }


@router.get("")
def list_tickets(user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Ticket).order_by(Ticket.id.desc()).all()
    return [
        {
            "id": t.id,
            "ticket_no": t.ticket_no,
            "amount": float(t.amount),
            "status": t.status.value,
            "decision": t.decision.value,
            "outcome": t.decision.value,
            "fraud_score": t.fraud_score,
            "sentiment": t.sentiment,
            "error_code": t.error_code,
            "error_message": t.error_message,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


@router.get("/{ticket_id}")
def get_ticket(
    ticket_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(Ticket, ticket_id)
    if t is None:
        raise HTTPException(404, "工单不存在")
    traces = [
        {
            "agent_name": tr.agent_name,
            "status": tr.status,
            "sequence_no": tr.sequence_no,
            "input_summary": tr.input_summary,
            "output_summary": tr.output_summary,
            "error_code": tr.error_code,
            "started_at": tr.started_at.isoformat() if tr.started_at else None,
            "ended_at": tr.ended_at.isoformat() if tr.ended_at else None,
        }
        for tr in sorted(t.traces, key=lambda x: x.sequence_no)
    ]
    return {
        "id": t.id,
        "ticket_no": t.ticket_no,
        "amount": float(t.amount),
        "ocr_text": t.ocr_text,
        "ocr_confidence": float(t.ocr_confidence) if t.ocr_confidence is not None else None,
        "fraud_score": t.fraud_score,
        "sentiment": t.sentiment,
        "status": t.status.value,
        "decision": t.decision.value,
        "outcome": t.decision.value,
        "error_code": t.error_code,
        "error_message": t.error_message,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "traces": traces,
    }


@router.post("/{ticket_id}/approve", response_model=ApproveResponse)
def approve_ticket(
    ticket_id: int,
    body: ApproveRequest,
    user=Depends(require_role(Role.SV)),
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
):
    token = acquire_approve_lock(redis, str(ticket_id))
    if token is None:
        raise HTTPException(409, "该工单正在被其他主管审批")
    try:
        t = db.get(Ticket, ticket_id)
        if t is None:
            raise HTTPException(404, "工单不存在")
        if t.status != TicketStatus.SUSPENDED:
            raise HTTPException(409, "工单不在挂起状态，无法审批")
        if t.decision == Decision.FAILED:
            raise HTTPException(409, "工单已失败，无法审批")
        db.add(Approval(ticket_id=t.id, reviewer_id=user.id, action=body.action, comment=body.comment))
        db.commit()
    except HTTPException:
        release_approve_lock(redis, str(ticket_id), token)  # 释放锁（token+Lua）
        raise
    except Exception:
        release_approve_lock(redis, str(ticket_id), token)
        raise
    # 先释放锁再入队 RESUME，避免审批请求与 Worker resume 相互阻塞
    release_approve_lock(redis, str(ticket_id), token)
    redis.xadd(
        settings.STREAM_KEY,
        {
            "type": "RESUME",
            "ticket_id": str(ticket_id),
            "thread_id": t.thread_id,
            "resume_action": body.action,
        },
    )
    return ApproveResponse(
        ticket_id=ticket_id,
        status=t.status.value,
        outcome=body.action,
        message="审批已记录，决策流正在恢复",
    )


@router.get("/{ticket_id}/events")
async def ticket_events(
    ticket_id: int,
    request: Request,
    user=Depends(get_current_user),
    redis=Depends(get_redis),
):
    """SSE 事件流：推送工单状态/轨迹变更事件，前端收到后调详情接口取完整数据。"""
    channel = f"{settings.EVENT_CHANNEL_PREFIX}:{ticket_id}"
    pubsub = redis.pubsub()
    pubsub.subscribe(channel)

    async def event_gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg.get("type") == "message":
                    yield {"event": "ticket_update", "data": msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"]}
                else:
                    yield {"event": "ping", "data": "keep-alive"}
        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()

    return EventSourceResponse(event_gen())
