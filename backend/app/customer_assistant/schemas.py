"""消费者助手接口的数据契约。"""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CustomerAssistantContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int | None = Field(default=None, gt=0)
    brand: str | None = Field(default=None, min_length=1, max_length=64)
    category: str | None = Field(default=None, min_length=1, max_length=32)


class CustomerAssistantReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    context: CustomerAssistantContext = Field(default_factory=CustomerAssistantContext)


class CatalogEvidence(BaseModel):
    source_url: str
    crawled_at: str | None


class CustomerAssistantReplyResponse(BaseModel):
    answer: str
    sources: list[CatalogEvidence]
    personalized: bool


class CustomerPrivacyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class CustomerPreferenceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any


class CustomerPreferenceResponse(BaseModel):
    key: str
    value: Any
    manual: bool


class CustomerPrivacyResponse(BaseModel):
    enabled: bool
    preferences: list[CustomerPreferenceResponse]
    ignored_keys: list[str]
