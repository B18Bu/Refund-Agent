"""仅检索已索引的主管可见政策片段。"""
from __future__ import annotations

import math

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.rag.models import RagChunk, RagDocument
from app.rag.schemas import KnowledgeEvidence


class RagRetriever:
    def __init__(self, session: Session, minimum_similarity: float = 0.65, limit: int = 5):
        self._session = session
        self._minimum_similarity = minimum_similarity
        self._limit = min(limit, 5)

    def search(self, query_embedding: list[float]) -> list[KnowledgeEvidence]:
        if self._session.bind and self._session.bind.dialect.name == "postgresql":
            rows = self._postgres_search(query_embedding)
        else:
            rows = self._sqlite_search(query_embedding)
        return [
            KnowledgeEvidence(
                content=row["content"], source=row["source"], section=row["section"],
                version=row["version"], similarity=round(float(row["similarity"]), 6), document_id=row["document_id"],
            )
            for row in rows
            if float(row["similarity"]) >= self._minimum_similarity
        ][:self._limit]

    def _postgres_search(self, query_embedding: list[float]) -> list[dict]:
        vector = "[" + ",".join(str(value) for value in query_embedding) + "]"
        statement = text("""
            SELECT c.content, d.id AS document_id, d.source_uri AS source, d.title AS section, d.version,
                   1 - (c.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM rag_chunks AS c
            JOIN rag_documents AS d ON d.id = c.document_id
            WHERE d.access_scope = :access_scope
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)
        return [dict(row) for row in self._session.execute(statement, {
            "embedding": vector, "access_scope": "supervisor", "limit": self._limit,
        }).mappings()]

    def _sqlite_search(self, query_embedding: list[float]) -> list[dict]:
        rows = (
            self._session.query(RagChunk, RagDocument)
            .join(RagDocument, RagDocument.id == RagChunk.document_id)
            .filter(RagDocument.access_scope == "supervisor")
            .all()
        )
        results = [
            {
                "content": chunk.content,
                "document_id": document.id,
                "source": document.source_uri,
                "section": document.title or f"片段 {chunk.chunk_index + 1}",
                "version": document.version,
                "similarity": _cosine_similarity(query_embedding, chunk.embedding),
            }
            for chunk, document in rows
        ]
        return sorted(results, key=lambda row: row["similarity"], reverse=True)[:self._limit]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0
