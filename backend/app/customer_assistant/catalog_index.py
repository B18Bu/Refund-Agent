"""将受控商品元数据写入消费者专用检索表。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session, joinedload

from app.commerce_models import Product, ProductStatus
from app.customer_assistant.embeddings import CatalogEmbeddingClient
from app.customer_assistant.models import CustomerCatalogChunk
from app.security.gateway import DLP


@dataclass(frozen=True)
class CustomerCatalogIndexResult:
    created_chunks: int = 0


class CustomerCatalogIndexer:
    def __init__(self, session: Session, embedding_client: CatalogEmbeddingClient):
        self._session = session
        self._embedding_client = embedding_client

    def index(self) -> CustomerCatalogIndexResult:
        created_chunks = 0
        current_chunks: set[tuple[int, str, str]] = set()
        pending_chunks = []
        products = (
            self._session.query(Product)
            .options(joinedload(Product.sources))
            .filter(Product.status == ProductStatus.ACTIVE)
            .all()
        )
        for product in products:
            content, _ = DLP.mask(_render_product_document(product))
            if not content:
                continue
            content_hash = _sha256(content)
            for source in product.sources:
                source_url = (source.source_url or "").strip()
                if not source_url:
                    continue
                chunk_key = (product.id, source_url, content_hash)
                current_chunks.add(chunk_key)
                source_hash = source.raw_hash or _sha256(f"{source.source_url}\n{content}")
                existing = self._session.query(CustomerCatalogChunk).filter_by(
                    product_id=product.id,
                    source_url=source_url,
                    content_hash=content_hash,
                ).one_or_none()
                if existing is not None:
                    existing.source_hash = source_hash
                    existing.crawled_at = source.last_seen_at
                    continue
                pending_chunks.append((
                    product.id,
                    source_url,
                    source.last_seen_at,
                    source_hash,
                    content,
                    content_hash,
                ))
        if pending_chunks:
            embeddings = self._embedding_client.embed([item[4] for item in pending_chunks])
            for item, embedding in zip(pending_chunks, embeddings):
                product_id, source_url, crawled_at, source_hash, content, content_hash = item
                self._session.add(CustomerCatalogChunk(
                    product_id=product_id,
                    source_url=source_url,
                    crawled_at=crawled_at,
                    source_hash=source_hash,
                    content=content,
                    content_hash=content_hash,
                    embedding=embedding,
                ))
                created_chunks += 1
        for chunk in self._session.query(CustomerCatalogChunk).all():
            if (chunk.product_id, chunk.source_url, chunk.content_hash) not in current_chunks:
                self._session.delete(chunk)
        return CustomerCatalogIndexResult(created_chunks=created_chunks)


def _render_product_document(product: Product) -> str:
    fields = (product.brand, product.name, product.model, product.description)
    return "\n".join(str(value).strip() for value in fields if value and str(value).strip())


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
