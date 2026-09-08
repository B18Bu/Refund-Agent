from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.customer_assistant.models import CustomerSupportCase
from app.deps import get_db, require_roles
from app.models import Role


router = APIRouter(prefix="/api/customer-support", tags=["customer-support"])


@router.get("/cases")
def list_cases(
    _user=Depends(require_roles(Role.CS, Role.SV)),
    db: Session = Depends(get_db),
):
    rows = db.query(CustomerSupportCase).order_by(CustomerSupportCase.id.desc()).all()
    return [
        {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "status": row.status,
            "trigger_reason": row.trigger_reason,
            "summary_masked": row.summary_masked,
            "assigned_to": row.assigned_to,
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
