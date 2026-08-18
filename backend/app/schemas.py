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


class TicketOut(BaseModel):
    id: int
    ticket_no: str
    amount: float
    status: str
    decision: str
    outcome: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    fraud_score: int | None = None
    sentiment: str | None = None
    ocr_confidence: float | None = None
    ocr_text: str | None = None
    created_at: str | None = None


class ApproveResponse(BaseModel):
    ticket_id: int
    status: str
    outcome: str
    message: str
