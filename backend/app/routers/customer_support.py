from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.customer_assistant.conversations import ConversationService
from app.customer_assistant.models import CustomerSupportCase
from app.customer_assistant.schemas import CustomerSupportMessageRequest, CustomerSupportMessageResponse
from app.deps import get_db, require_roles
from app.models import Role


router = APIRouter(prefix="/api/customer-support", tags=["customer-support"])


@router.get("/cases")
def list_cases(
    _user=Depends(require_roles(Role.CS, Role.SV)),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CustomerSupportCase)
        .filter(CustomerSupportCase.status.in_(("OPEN", "IN_PROGRESS")))
        .order_by(CustomerSupportCase.id.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "status": row.status,
            "trigger_reason": row.trigger_reason,
            "summary_masked": row.summary_masked,
            "assigned_to": row.assigned_to,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


@router.post("/cases/{case_id}/assign")
def assign_case(case_id: int, user=Depends(require_roles(Role.CS, Role.SV)), db: Session = Depends(get_db)):
    result = db.execute(update(CustomerSupportCase).where(CustomerSupportCase.id == case_id, CustomerSupportCase.status == "OPEN").values(status="IN_PROGRESS", assigned_to=user.id))
    if result.rowcount != 1: raise HTTPException(409, "客服工单无法领取")
    db.commit()
    return {"id": case_id, "status": "IN_PROGRESS", "assigned_to": user.id}


@router.post("/cases/{case_id}/resolve")
def resolve_case(case_id: int, user=Depends(require_roles(Role.CS, Role.SV)), db: Session = Depends(get_db)):
    result = db.execute(update(CustomerSupportCase).where(CustomerSupportCase.id == case_id, CustomerSupportCase.status == "IN_PROGRESS", CustomerSupportCase.assigned_to == user.id).values(status="RESOLVED"))
    if result.rowcount != 1: raise HTTPException(409, "客服工单无法关闭")
    db.commit()
    return {"id": case_id, "status": "RESOLVED"}


def _message_response(message) -> CustomerSupportMessageResponse:
    return CustomerSupportMessageResponse(
        id=message.id,
        sender=message.sender,
        content=message.content_masked,
        evidence=message.evidence or {},
        created_at=message.created_at.isoformat() if message.created_at else None,
    )


@router.get("/cases/{case_id}/messages", response_model=list[CustomerSupportMessageResponse])
def list_case_messages(
    case_id: int,
    user=Depends(require_roles(Role.CS, Role.SV)),
    db: Session = Depends(get_db),
):
    case = (
        db.query(CustomerSupportCase)
        .filter(
            CustomerSupportCase.id == case_id,
            CustomerSupportCase.status.in_(("OPEN", "IN_PROGRESS")),
        )
        .one_or_none()
    )
    if case is None:
        raise HTTPException(404, "客服工单不存在")
    return [_message_response(message) for message in ConversationService(db).list_messages(case.conversation_id, user.id, user.role)]


@router.post("/cases/{case_id}/messages", response_model=CustomerSupportMessageResponse)
def send_case_message(
    case_id: int,
    body: CustomerSupportMessageRequest,
    user=Depends(require_roles(Role.CS, Role.SV)),
    db: Session = Depends(get_db),
):
    try:
        message = ConversationService(db).add_agent_message(case_id, user.id, body.content)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return _message_response(message)
