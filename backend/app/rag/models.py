"""主管政策依据 RAG 的 SQLAlchemy 数据模型。"""
import json
import math
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import UserDefinedType

from app.db import Base


class Vector512(UserDefinedType):
    """与 pgvector 显式迁移对应的固定维度向量列。"""

    cache_ok = True

    def get_col_spec(self, **_kwargs) -> str:
        return "VECTOR(512)"

    def bind_processor(self, _dialect):
        def process(value):
            vector = self._validate(value)
            if vector is None:
                return None
            return "[" + ",".join(repr(item) for item in vector) + "]"

        return process

    def result_processor(self, _dialect, _coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            if isinstance(value, str):
                value = json.loads(value)
            return self._validate(value)

        return process

    @staticmethod
    def _validate(value):
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("embedding 必须是长度为 512 的列表")
        if len(value) != 512:
            raise ValueError("embedding 必须包含 512 个维度")
        if any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(item)
            for item in value
        ):
            raise ValueError("embedding 必须只包含有限数值")
        return [float(item) for item in value]


class RagDocument(Base):
    """已批准政策来源的版本化元数据。"""

    __tablename__ = "rag_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_uri: Mapped[str] = mapped_column(String(512))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(64))
    access_scope: Mapped[str] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["RagChunk"]] = relationship(back_populates="document")


class RagChunk(Base):
    """脱敏后的政策文本分块及其 pgvector embedding。"""

    __tablename__ = "rag_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_rag_chunks_document_index"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("rag_documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector512())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[RagDocument] = relationship(back_populates="chunks")


class RagQueryLog(Base):
    """仅保存脱敏查询摘要与命中来源的主管检索审计记录。"""

    __tablename__ = "rag_query_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    access_scope: Mapped[str] = mapped_column(String(32))
    query_summary: Mapped[str] = mapped_column(Text)
    hit_document_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
