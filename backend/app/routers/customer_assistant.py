"""消费者专用商品咨询接口。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.customer_assistant.preferences import (
    delete_preference, disable_privacy, enable_privacy, privacy_snapshot, rebuild_preferences,
    restore_preference, set_manual_preference,
)
from app.customer_assistant.schemas import (
    CatalogEvidence, CustomerAssistantReplyRequest, CustomerAssistantReplyResponse,
    CustomerConversationMessagesResponse, CustomerSupportConversationResponse,
    CustomerPreferenceResponse, CustomerPreferenceUpdateRequest, CustomerPrivacyResponse,
    CustomerPrivacyUpdateRequest, CustomerSupportMessageResponse,
)
from app.customer_assistant.service import CustomerAssistantService
from app.customer_assistant.conversations import ConversationService
from app.customer_assistant.models import CustomerSupportCase, CustomerSupportConversation, CustomerSupportMessage
from app.deps import get_db, require_role
from app.models import Role


router = APIRouter(prefix="/api/customer-assistant", tags=["customer-assistant"])

@router.get("/conversations", response_model=list[CustomerSupportConversationResponse])
def list_conversations(user=Depends(require_role(Role.CUSTOMER)), db: Session = Depends(get_db)):
    return ConversationService(db).list_conversations(user.id)

@router.post("/conversations")
def create_conversation(user=Depends(require_role(Role.CUSTOMER)), db: Session = Depends(get_db)):
    row = ConversationService(db).create_conversation(user.id)
    return {"id": row.id, "status": row.status}

@router.post("/conversations/{conversation_id}/messages")
def send_message(conversation_id: int, body: CustomerAssistantReplyRequest, user=Depends(require_role(Role.CUSTOMER)), db: Session = Depends(get_db)):
    try: result = ConversationService(db).reply(conversation_id, user.id, body.message)
    except LookupError as error: raise HTTPException(404, str(error)) from error
    except ValueError as error: raise HTTPException(409, str(error)) from error
    return {"conversation_id": result.conversation_id, "answer": result.answer, "intent": result.intent, "evidence": result.evidence}


@router.get("/conversations/{conversation_id}/messages", response_model=CustomerConversationMessagesResponse)
def list_messages(conversation_id: int, user=Depends(require_role(Role.CUSTOMER)), db: Session = Depends(get_db)):
    try:
        messages = ConversationService(db).list_messages(conversation_id, user.id, user.role)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    case = db.query(CustomerSupportCase).filter_by(conversation_id=conversation_id).one_or_none()
    return CustomerConversationMessagesResponse(
        status=case.status if case else "NO_CASE",
        messages=[
            CustomerSupportMessageResponse(
                id=message.id,
                sender=message.sender,
                content=message.content_masked,
                evidence=message.evidence or {},
                created_at=message.created_at.isoformat() if message.created_at else None,
            )
            for message in messages
        ],
    )

@router.post("/conversations/{conversation_id}/escalations")
def escalate(conversation_id: int, user=Depends(require_role(Role.CUSTOMER)), db: Session = Depends(get_db)):
    try: row = ConversationService(db).escalate(conversation_id, user.id)
    except LookupError as error: raise HTTPException(404, str(error)) from error
    return {"case_id": row.id, "status": row.status}


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


def _privacy_response(db: Session, user_id: int) -> CustomerPrivacyResponse:
    enabled, preferences, ignored_keys = privacy_snapshot(db, user_id)
    return CustomerPrivacyResponse(
        enabled=enabled,
        preferences=[CustomerPreferenceResponse(key=key, value=value, manual=manual) for key, value, manual in preferences],
        ignored_keys=ignored_keys,
    )


@router.get("/privacy", response_model=CustomerPrivacyResponse)
def get_privacy(user=Depends(require_role(Role.CUSTOMER)), db: Session = Depends(get_db)):
    return _privacy_response(db, user.id)


@router.put("/privacy", response_model=CustomerPrivacyResponse)
def update_privacy(
    body: CustomerPrivacyUpdateRequest,
    user=Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    if body.enabled:
        enable_privacy(db, user.id)
        rebuild_preferences(db, user.id, datetime.utcnow())
    else:
        disable_privacy(db, user.id)
    return _privacy_response(db, user.id)


@router.put("/privacy/preferences/{preference_key}", response_model=CustomerPrivacyResponse)
def update_preference(
    preference_key: str,
    body: CustomerPreferenceUpdateRequest,
    user=Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    try:
        set_manual_preference(db, user.id, preference_key, body.value)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _privacy_response(db, user.id)


@router.delete("/privacy/preferences/{preference_key}", response_model=CustomerPrivacyResponse)
def delete_customer_preference(
    preference_key: str,
    user=Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    try:
        delete_preference(db, user.id, preference_key)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _privacy_response(db, user.id)


@router.delete("/privacy/ignored/{preference_key}", response_model=CustomerPrivacyResponse)
def restore_customer_preference(
    preference_key: str,
    user=Depends(require_role(Role.CUSTOMER)),
    db: Session = Depends(get_db),
):
    try:
        restore_preference(db, user.id, preference_key)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _privacy_response(db, user.id)
