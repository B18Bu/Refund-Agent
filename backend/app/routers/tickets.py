"""工单路由：创建/列表/详情/审批 + SSE 事件流。

审批采用「入队 RESUME 消息由 Worker 串行 resume」方式（三方对齐：API 不直接 resume LangGraph）。
"""
import json
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.deps import get_current_user, get_db, require_role, require_roles
from app.idempotency import resolve_idempotency
from app.locks import acquire_approve_lock, release_approve_lock
from app.models import Approval, Decision, Role, Ticket, TicketStatus
from app.commerce_models import ReturnRequest, Order, OrderItem
from app.evaluation.models import AgentEvaluationRun
from app.evaluation.schemas import serialize_evaluation
from app.redis_client import get_redis
from app.storage import save_upload
from app.schemas import (
    ApproveRequest,
    ApproveResponse,
    TicketCreate,
    outcome_text,
    sentiment_text,
    status_text,
)

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("/{ticket_id}/evaluation")
def get_ticket_evaluation(
    ticket_id: int,
    _user=Depends(require_role(Role.SV)),
    db: Session = Depends(get_db),
):
    row = (
        db.query(AgentEvaluationRun)
        .filter(AgentEvaluationRun.ticket_id == ticket_id)
        .order_by(AgentEvaluationRun.id.desc())
        .first()
    )
    if row is None:
        return {"available": False, "status": "NOT_AVAILABLE"}
    return {"available": True, "status": row.evaluation_status, "record": serialize_evaluation(row)}


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
                "status_text": status_text(ticket.status.value),
                "outcome": ticket.decision.value,
                "outcome_text": outcome_text(ticket.decision.value),
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
        "status_text": status_text(ticket.status.value),
        "outcome": ticket.decision.value,
        "outcome_text": outcome_text(ticket.decision.value),
    }


@router.post("/with-files")
async def create_ticket_with_files(
    amount: float = Form(...),
    files: list[UploadFile] = File(default=[]),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
    redis=Depends(get_redis),
    x_idempotency_key: str | None = Header(None),
):
    """一次完成建单 + 上传凭证图片（multipart）。保证 Worker 消费时图片已就绪。

    修复时序缺陷：原流程「先建单入队，再传图」会导致 Worker 用空图片先跑 OCR
    → 置信度 0 → 误转人工。此接口先存图再入队，图片路径随工单一并落库。
    """
    idem_key = x_idempotency_key or uuid.uuid4().hex
    ticket_no = uuid.uuid4().hex
    redis_key = f"idem:{user.id}:{idem_key}"
    existing = resolve_idempotency(redis, redis_key, str(ticket_no))
    if existing is not None:
        ticket = db.query(Ticket).filter(Ticket.ticket_no == existing).first()
        if ticket:
            return {
                "ticket_id": ticket.id,
                "ticket_no": ticket.ticket_no,
                "status": ticket.status.value,
                "status_text": status_text(ticket.status.value),
                "outcome": ticket.decision.value,
                "outcome_text": outcome_text(ticket.decision.value),
            }

    if len(files) > 3:
        raise HTTPException(413, "最多上传 3 张图片")

    image_paths: list[str] = []
    for uf in files:
        meta = await save_upload(uf)
        image_paths.append(meta["storage_key"])

    ticket = Ticket(
        ticket_no=ticket_no,
        user_id=user.id,
        amount=amount,
        image_paths=image_paths,
        status=TicketStatus.RUNNING,
        decision=Decision.PENDING,
        thread_id=uuid.uuid4().hex,
        idempotency_key=idem_key,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    # 图片已随工单落库，再入队 START（Worker 读到的 image_paths 非空）
    redis.xadd(
        settings.STREAM_KEY,
        {"type": "START", "ticket_id": str(ticket.id), "thread_id": ticket.thread_id},
    )
    return {
        "ticket_id": ticket.id,
        "ticket_no": ticket.ticket_no,
        "status": ticket.status.value,
        "status_text": status_text(ticket.status.value),
        "outcome": ticket.decision.value,
        "outcome_text": outcome_text(ticket.decision.value),
        "uploaded_files": len(image_paths),
    }


@router.get("")
def list_tickets(user=Depends(get_current_user), db: Session = Depends(get_db)):
    # 只返回最近 N 条，避免全表扫描拖垮列表接口（压测/大数据量场景）
    query = db.query(Ticket)
    if user.role != Role.SV:
        query = query.filter(Ticket.user_id == user.id)
    rows = query.order_by(Ticket.id.desc()).limit(100).all()
    return [
        {
            "id": t.id,
            "ticket_no": t.ticket_no,
            "amount": float(t.amount),
            "description": t.description,
            "trace_id": t.trace_id,
            "status": t.status.value,
            "status_text": status_text(t.status.value),
            "decision": t.decision.value,
            "outcome": t.decision.value,
            "outcome_text": outcome_text(t.decision.value),
            "fraud_score": t.fraud_score,
            "sentiment": t.sentiment,
            "sentiment_text": sentiment_text(t.sentiment),
            "decision_reasons": t.decision_reasons,
            "evidence_audit": t.evidence_audit,
            "management_suggestion": t.management_suggestion,
            "error_code": t.error_code,
            "error_message": t.error_message,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


@router.get("/service/returns")
def list_manual_returns(
    _user=Depends(require_roles(Role.CS, Role.SV)),
    db: Session = Depends(get_db),
):
    """客服/主管共用的人工退款队列，仅返回仍可审批的挂起工单。"""
    rows = (
        db.query(ReturnRequest, Ticket, OrderItem)
        .join(Ticket, ReturnRequest.ticket_id == Ticket.id)
        .join(OrderItem, ReturnRequest.order_item_id == OrderItem.id)
        .filter(Ticket.status == TicketStatus.SUSPENDED)
        .order_by(ReturnRequest.id.asc())
        .all()
    )
    return [
        {
            "id": return_request.id,
            "ticket_id": ticket.id,
            "return_no": return_request.return_no,
            "order_id": return_request.order_id,
            "order_item_id": return_request.order_item_id,
            "reason": return_request.reason,
            "description": return_request.description,
            "status": return_request.status.value,
            "amount": float(ticket.amount),
            "decision_reasons": ticket.decision_reasons or [],
            "evidence_paths": return_request.evidence_paths or [],
            "product_name": (item.product_snapshot_json or {}).get("name"),
        }
        for return_request, ticket, item in rows
    ]


@router.get("/{ticket_id}")
def get_ticket(
    ticket_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    t = db.get(Ticket, ticket_id)
    if t is None or (user.role != Role.SV and t.user_id != user.id):
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
    return_request = db.query(ReturnRequest).filter(ReturnRequest.ticket_id == t.id).first()
    commerce_context = None
    if return_request is not None:
        order = db.get(Order, return_request.order_id)
        item = db.get(OrderItem, return_request.order_item_id)
        snapshot = item.product_snapshot_json if item is not None else {}
        commerce_context = {
            "order_no": order.order_no if order else None,
            "return_no": return_request.return_no,
            "product_name": snapshot.get("name"),
            "return_reason": return_request.reason,
        }
    return {
        "id": t.id,
        "ticket_no": t.ticket_no,
        "amount": float(t.amount),
        "description": t.description,
        "commerce_context": commerce_context,
        "trace_id": t.trace_id,
        "ocr_text": t.ocr_text,
        "ocr_confidence": float(t.ocr_confidence) if t.ocr_confidence is not None else None,
        "fraud_score": t.fraud_score,
        "sentiment": t.sentiment,
        "sentiment_text": sentiment_text(t.sentiment),
        "decision_reasons": t.decision_reasons,
        "evidence_audit": t.evidence_audit,
        "management_suggestion": t.management_suggestion,
        "status": t.status.value,
        "status_text": status_text(t.status.value),
        "decision": t.decision.value,
        "outcome": t.decision.value,
        "outcome_text": outcome_text(t.decision.value),
        "error_code": t.error_code,
        "error_message": t.error_message,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "traces": traces,
    }


@router.post("/{ticket_id}/approve", response_model=ApproveResponse)
def approve_ticket(
    ticket_id: int,
    body: ApproveRequest,
    user=Depends(require_roles(Role.CS, Role.SV)),
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
        if user.role == Role.CS and db.query(ReturnRequest.id).filter(ReturnRequest.ticket_id == t.id).first() is None:
            raise HTTPException(403, "客服仅可审批退款申请")
        if t.decision == Decision.FAILED:
            raise HTTPException(409, "工单已失败，无法审批")
        # 三方对齐最终防线：DB 条件更新（原子），仅当仍为 SUSPENDED 才允许审批，
        # 并将状态原子地推进为 RUNNING（占位），防止锁释放空窗期被第二个主管重复审批。
        claimed = (
            db.query(Ticket)
            .filter(Ticket.id == ticket_id, Ticket.status == TicketStatus.SUSPENDED)
            .update(
                {"status": TicketStatus.RUNNING},
                synchronize_session=False,
            )
        )
        if claimed == 0:
            raise HTTPException(409, "工单不在挂起状态，无法审批")
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
        status=TicketStatus.RUNNING.value,
        status_text=status_text(TicketStatus.RUNNING.value),
        outcome=body.action,
        outcome_text=outcome_text("APPROVED" if body.action == "APPROVE" else "REJECTED"),
        message="审批已记录，决策流正在恢复",
    )


@router.get("/{ticket_id}/events")
async def ticket_events(
    ticket_id: int,
    request: Request,
    user=Depends(get_current_user),
    redis=Depends(get_redis),
    db: Session = Depends(get_db),
):
    """SSE 事件流：推送工单状态/轨迹变更事件，前端收到后调详情接口取完整数据。"""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or (user.role != Role.SV and ticket.user_id != user.id):
        raise HTTPException(404, "工单不存在")
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
