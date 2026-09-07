"""将白名单政策资料以脱敏内容哈希幂等写入 RAG 表。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.rag.documents import scan_whitelisted_documents
from app.rag.embeddings import EmbeddingClient
from app.rag.models import RagChunk, RagDocument
from app.security.gateway import DLP


@dataclass(frozen=True)
class IndexResult:
    created_documents: int = 0
    created_chunks: int = 0


class RagIndexer:
    def __init__(self, session: Session, embedding_client: EmbeddingClient, repository_root: Path):
        self._session = session
        self._embedding_client = embedding_client
        self._root = repository_root

    def index(self) -> IndexResult:
        created_documents = 0
        created_chunks = 0
        for source in scan_whitelisted_documents(self._root):
            masked_content, _ = DLP.mask(source.content)
            source_hash = _sha256(masked_content)
            document = self._session.query(RagDocument).filter_by(source_hash=source_hash).one_or_none()
            if document is not None:
                continue
            document = RagDocument(
                source_uri=source.source_uri,
                source_hash=source_hash,
                version=source_hash[:12],
                access_scope="supervisor",
                title=source.title,
            )
            self._session.add(document)
            self._session.flush()
            created_documents += 1
            chunks = _split(masked_content)
            vectors = self._embedding_client.embed(chunks)
            for chunk_index, (content, embedding) in enumerate(zip(chunks, vectors, strict=True)):
                self._session.add(RagChunk(
                    document_id=document.id,
                    chunk_index=chunk_index,
                    content=content,
                    content_hash=_sha256(content),
                    embedding=embedding,
                ))
                created_chunks += 1
        return IndexResult(created_documents, created_chunks)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split(content: str, limit: int = 1200) -> list[str]:
    content = content.strip()
    return [content[index:index + limit] for index in range(0, len(content), limit)] if content else []


def main() -> None:
    from app.db import SessionLocal

    repository_root = Path(__file__).resolve().parents[3]
    with SessionLocal() as session:
        try:
            result = RagIndexer(session, EmbeddingClient(), repository_root).index()
            session.commit()
        except Exception:
            session.rollback()
            raise
    print(f"已索引文档 {result.created_documents} 个，分块 {result.created_chunks} 个")


if __name__ == "__main__":
    main()
