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
    CustomerPreferenceResponse, CustomerPreferenceUpdateRequest, CustomerPrivacyResponse,
    CustomerPrivacyUpdateRequest,
)
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
