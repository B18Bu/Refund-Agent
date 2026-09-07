"""消费者专用商品咨询接口。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.customer_assistant.schemas import CatalogEvidence, CustomerAssistantReplyRequest, CustomerAssistantReplyResponse
from app.customer_assistant.service import CustomerAssistantService
from app.deps import get_db, require_role
from app.models import Role


router = APIRouter(prefix="/api/customer-assistant", tags=["customer-assistant"])


@router.post("/reply", response_model=CustomerAssistantReplyResponse)
def reply(
    body: CustomerAssistantReplyRequest,
    user=Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    result = CustomerAssistantService(db).reply(user, body.message, body.context.model_dump(exclude_none=True))
    return CustomerAssistantReplyResponse(
        answer=result.answer,
        sources=[CatalogEvidence(source_url=source.source_url, crawled_at=source.crawled_at) for source in result.sources],
        personalized=result.personalized,
    )
