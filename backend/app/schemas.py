"""Pydantic 请求/响应模型。"""
from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 7200


class TicketCreate(BaseModel):
    amount: float = Field(gt=0, le=100000)
    image_paths: list[str] = []


class FileUploadResult(BaseModel):
    id: int
    filename: str
    content_type: str
    size_bytes: int


class FileUploadResponse(BaseModel):
    ticket_id: int
    files: list[FileUploadResult]


class ApproveRequest(BaseModel):
    action: Literal["APPROVE", "REJECT"]
    comment: str | None = None


# ===== 状态 → 中文展示（API 返回时附加，供前端直接展示） =====
STATUS_TEXT_CN: dict[str, str] = {
    "RUNNING": "处理中",
    "SUSPENDED": "待人工审批",
    "COMPLETED": "已完成",
}
OUTCOME_TEXT_CN: dict[str, str] = {
    "PENDING": "待定",
    "AUTO_REFUNDED": "自动退赔",
    "APPROVED": "已批准",
    "REJECTED": "已拒绝",
    "FAILED": "处理失败",
}
SENTIMENT_TEXT_CN: dict[str, str] = {
    "LOW": "低",
    "MEDIUM": "中",
    "HIGH": "高",
}


def status_text(status: str) -> str:
    return STATUS_TEXT_CN.get(status, status)


def outcome_text(outcome: str) -> str:
    return OUTCOME_TEXT_CN.get(outcome, outcome)


def sentiment_text(sentiment: str | None) -> str | None:
    if sentiment is None:
        return None
    return SENTIMENT_TEXT_CN.get(sentiment, sentiment)


class TicketOut(BaseModel):
    id: int
    ticket_no: str
    amount: float
    status: str
    status_text: str = ""          # 中文状态（如「待人工审批」）
    decision: str
    outcome: str | None = None
    outcome_text: str = ""         # 中文结果（如「自动退赔」）
    error_code: str | None = None
    error_message: str | None = None
    fraud_score: int | None = None
    sentiment: str | None = None
    sentiment_text: str | None = None   # 中文舆情等级
    ocr_confidence: float | None = None
    ocr_text: str | None = None
    created_at: str | None = None


class ApproveResponse(BaseModel):
    ticket_id: int
    status: str
    status_text: str = ""
    outcome: str
    outcome_text: str = ""
    message: str
