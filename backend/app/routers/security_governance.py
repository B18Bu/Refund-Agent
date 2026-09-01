"""主管专用的安全治理摘要接口。"""
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db, require_role
from app.models import Role
from app.security.governance import build_summary


router = APIRouter(prefix="/api/security-governance", tags=["security-governance"])


@router.get("/summary")
def get_security_governance_summary(
    _user=Depends(require_role(Role.SV)),
    db: Session = Depends(get_db),
):
    return build_summary(
        db,
        red_blue_path=Path(settings.SECURITY_RED_BLUE_REPORT_PATH),
        dlp_path=Path(settings.SECURITY_DLP_REPORT_PATH),
        audit_path=Path(settings.SECURITY_AUDIT_REPORT_PATH),
    )
