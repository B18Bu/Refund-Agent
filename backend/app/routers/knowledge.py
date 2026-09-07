"""主管政策依据读取接口；只返回原文证据，不参与退赔决策。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db, require_role
from app.models import Role, Ticket, User
from app.rag.schemas import KnowledgeResult
from app.rag.service import KnowledgeService

router = APIRouter(tags=["knowledge"])


@router.get("/api/tickets/{ticket_id}/knowledge", response_model=KnowledgeResult)
def get_ticket_knowledge(
    ticket_id: int,
    user: User = Depends(require_role(Role.SV)),
    db: Session = Depends(get_db),
):
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(404, "工单不存在")
    return KnowledgeService(db).search_ticket(user, ticket)


@router.get("/api/evaluations/knowledge", response_model=KnowledgeResult)
def get_evaluation_knowledge(
    user: User = Depends(require_role(Role.SV)),
    db: Session = Depends(get_db),
):
    return KnowledgeService(db).search_evaluations(user)
