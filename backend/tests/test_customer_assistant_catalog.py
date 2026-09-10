import inspect
from datetime import datetime
from unittest.mock import AsyncMock, Mock

from app.catalog_initialization import CatalogResult, CatalogStatus
from app.commerce_models import Product, ProductSource, ProductStatus
from app.models import User  # noqa: F401


class FakeEmbedding:
    def embed(self, texts):
        return [[0.25] * 512 for _ in texts]


class RecordingEmbedding(FakeEmbedding):
    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return super().embed(texts)


def test_customer_catalog_embedding_uses_local_service_in_single_container():
    from app.customer_assistant.embeddings import CATALOG_EMBEDDING_SERVICE_URL

    assert CATALOG_EMBEDDING_SERVICE_URL == "http://127.0.0.1:8080"


def _product_with_source(db_session, *, status, description, source_url):
    product = Product(
        brand="测试品牌",
        name="测试商品",
        model="X1",
        description=description,
        status=status,
    )
    db_session.add(product)
    db_session.flush()
    db_session.add(ProductSource(
        product_id=product.id,
        source_site="example",
        source_url=source_url,
        external_id=f"external-{product.id}",
        raw_hash=f"{'a' * 63}{product.id}",
        last_seen_at=datetime(2026, 9, 7, 10, 30),
    ))
    db_session.commit()
    return product


def test_index_excludes_unavailable_products_and_preserves_source(db_session):
    from app.customer_assistant.catalog_index import CustomerCatalogIndexer
    from app.customer_assistant.models import CustomerCatalogChunk

    active = _product_with_source(
        db_session,
        status=ProductStatus.ACTIVE,
        description="适合日常使用",
        source_url="https://example.test/product",
    )
    _product_with_source(
        db_session,
        status=ProductStatus.UNAVAILABLE,
        description="不能被索引",
        source_url="https://example.test/unavailable",
    )

    result = CustomerCatalogIndexer(db_session, FakeEmbedding()).index()

    chunks = db_session.query(CustomerCatalogChunk).all()
    assert result.created_chunks == 1
    assert len(chunks) == 1
    assert chunks[0].product_id == active.id
    assert chunks[0].source_url == "https://example.test/product"
    assert chunks[0].source_hash == "a" * 63 + str(active.id)
    assert chunks[0].crawled_at == datetime(2026, 9, 7, 10, 30)
    assert chunks[0].embedding == [0.25] * 512


def test_index_batches_embeddings_for_multiple_new_products(db_session):
    from app.customer_assistant.catalog_index import CustomerCatalogIndexer

    _product_with_source(
        db_session,
        status=ProductStatus.ACTIVE,
        description="第一件商品",
        source_url="https://example.test/one",
    )
    _product_with_source(
        db_session,
        status=ProductStatus.ACTIVE,
        description="第二件商品",
        source_url="https://example.test/two",
    )
    embedding = RecordingEmbedding()

    CustomerCatalogIndexer(db_session, embedding).index()

    assert len(embedding.calls) == 1
    assert len(embedding.calls[0]) == 2


def test_index_masks_sensitive_product_text_and_keeps_consumer_tables_isolated(db_session):
    from app.customer_assistant.catalog_index import CustomerCatalogIndexer
    from app.customer_assistant.models import CustomerCatalogChunk

    _product_with_source(
        db_session,
        status=ProductStatus.ACTIVE,
        description="咨询电话 13812345678，联系 help@example.com",
        source_url="https://example.test/product",
    )

    CustomerCatalogIndexer(db_session, FakeEmbedding()).index()

    chunk = db_session.query(CustomerCatalogChunk).one()
    assert "138****5678" in chunk.content
    assert "h***@example.com" in chunk.content


def test_customer_catalog_index_and_worker_do_not_depend_on_app_rag_modules():
    from app.customer_assistant import catalog_index
    from app.worker import catalog_consumer

    assert "app.rag" not in inspect.getsource(catalog_index)
    assert "app.rag" not in inspect.getsource(catalog_consumer)


def test_reindex_refreshes_source_traceability_when_product_content_is_unchanged(db_session):
    from app.customer_assistant.catalog_index import CustomerCatalogIndexer
    from app.customer_assistant.models import CustomerCatalogChunk

    product = _product_with_source(
        db_session,
        status=ProductStatus.ACTIVE,
        description="适合日常使用",
        source_url="https://example.test/product",
    )
    indexer = CustomerCatalogIndexer(db_session, FakeEmbedding())
    indexer.index()
    source = product.sources[0]
    source.raw_hash = "b" * 64
    source.last_seen_at = datetime(2026, 9, 8, 9, 0)
    db_session.commit()

    result = indexer.index()

    chunk = db_session.query(CustomerCatalogChunk).one()
    assert result.created_chunks == 0
    assert chunk.source_hash == "b" * 64
    assert chunk.crawled_at == datetime(2026, 9, 8, 9, 0)


def test_reindex_removes_chunk_when_product_becomes_unavailable(db_session):
    from app.customer_assistant.catalog_index import CustomerCatalogIndexer
    from app.customer_assistant.models import CustomerCatalogChunk

    product = _product_with_source(
        db_session,
        status=ProductStatus.ACTIVE,
        description="适合日常使用",
        source_url="https://example.test/product",
    )
    indexer = CustomerCatalogIndexer(db_session, FakeEmbedding())
    indexer.index()
    product.status = ProductStatus.UNAVAILABLE
    db_session.commit()

    indexer.index()

    assert db_session.query(CustomerCatalogChunk).count() == 0


def test_index_skips_product_source_without_nonblank_url(db_session):
    from app.customer_assistant.catalog_index import CustomerCatalogIndexer
    from app.customer_assistant.models import CustomerCatalogChunk

    _product_with_source(
        db_session,
        status=ProductStatus.ACTIVE,
        description="适合日常使用",
        source_url="   ",
    )

    result = CustomerCatalogIndexer(db_session, FakeEmbedding()).index()

    assert result.created_chunks == 0
    assert db_session.query(CustomerCatalogChunk).count() == 0


def test_reindex_removes_chunk_for_superseded_product_content(db_session):
    from app.customer_assistant.catalog_index import CustomerCatalogIndexer
    from app.customer_assistant.models import CustomerCatalogChunk

    product = _product_with_source(
        db_session,
        status=ProductStatus.ACTIVE,
        description="旧款说明",
        source_url="https://example.test/product",
    )
    indexer = CustomerCatalogIndexer(db_session, FakeEmbedding())
    indexer.index()
    product.description = "新款说明"
    db_session.commit()

    indexer.index()

    chunks = db_session.query(CustomerCatalogChunk).all()
    assert len(chunks) == 1
    assert "新款说明" in chunks[0].content


def test_customer_catalog_tables_require_explicit_migration_and_are_not_created_at_startup(monkeypatch):
    from app import main
    from app.customer_assistant.models import CustomerCatalogChunk

    calls = []
    monkeypatch.setattr(main.Base.metadata, "create_all", lambda **kwargs: calls.append(kwargs))

    main.init_db()

    table_names = {table.name for table in calls[0]["tables"]}
    assert CustomerCatalogChunk.__tablename__ not in table_names


def test_catalog_worker_indexes_only_after_successful_refresh(monkeypatch):
    from app.worker import catalog_consumer

    db = Mock()
    index = Mock()
    monkeypatch.setattr(catalog_consumer, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        catalog_consumer,
        "run_catalog_initialization",
        AsyncMock(
            return_value=CatalogResult(CatalogStatus.INITIALIZATION_FAILED, "SOURCE_FETCH_FAILED")
        ),
    )
    monkeypatch.setattr(catalog_consumer, "CustomerCatalogIndexer", lambda *_args: Mock(index=index))

    catalog_consumer.run_once()

    index.assert_not_called()


def test_catalog_worker_skips_index_when_refresh_uses_cached_catalog(monkeypatch):
    from app.worker import catalog_consumer

    db = Mock()
    index = Mock()
    monkeypatch.setattr(catalog_consumer, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        catalog_consumer,
        "run_catalog_initialization",
        AsyncMock(return_value=CatalogResult(CatalogStatus.READY, used_cached_catalog=True)),
    )
    monkeypatch.setattr(catalog_consumer, "CustomerCatalogIndexer", lambda *_args: Mock(index=index))

    catalog_consumer.run_once()

    index.assert_not_called()
    db.commit.assert_not_called()


def test_catalog_worker_indexes_after_fresh_successful_refresh(monkeypatch):
    from app.worker import catalog_consumer

    db = Mock()
    index = Mock()
    monkeypatch.setattr(catalog_consumer, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        catalog_consumer,
        "run_catalog_initialization",
        AsyncMock(return_value=CatalogResult(CatalogStatus.READY)),
    )
    monkeypatch.setattr(catalog_consumer, "CustomerCatalogIndexer", lambda *_args: Mock(index=index))

    catalog_consumer.run_once()

    index.assert_called_once_with()
    db.commit.assert_called_once_with()
