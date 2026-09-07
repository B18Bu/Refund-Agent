"""主管政策依据检索的最小响应类型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeEvidence(BaseModel):
    content: str
    source: str
    section: str | None = None
    version: str
    similarity: float
    document_id: int | None = Field(default=None, exclude=True)


class KnowledgeResult(BaseModel):
    available: bool
    query_id: int | None = None
    status: str
    results: list[KnowledgeEvidence]

    @classmethod
    def ok(cls, results: list[dict] | list[KnowledgeEvidence]) -> "KnowledgeResult":
        return cls(available=True, status="ok", results=results)

    @classmethod
    def empty(cls) -> "KnowledgeResult":
        return cls(available=True, status="empty", results=[])

    @classmethod
    def unavailable(cls) -> "KnowledgeResult":
        return cls(available=False, status="unavailable", results=[])
