from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

MIGRATION = Path(__file__).parents[1] / "migrations" / "20260906_add_rag_knowledge.sql"


def test_rag_schema_uses_pgvector_migration():
    from app.rag.models import RagChunk, RagDocument, RagQueryLog

    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "create extension if not exists vector" in sql
    assert {RagDocument.__tablename__, RagChunk.__tablename__, RagQueryLog.__tablename__} == {
        "rag_documents",
        "rag_chunks",
        "rag_query_logs",
    }
    assert "vector(512)" in sql


def test_rag_models_keep_only_minimum_traceability_and_audit_fields():
    from app.rag.models import RagChunk, RagDocument, RagQueryLog

    document_columns = set(RagDocument.__table__.columns.keys())
    chunk_columns = set(RagChunk.__table__.columns.keys())
    query_log_columns = set(RagQueryLog.__table__.columns.keys())

    assert {"source_uri", "source_hash", "version", "access_scope"} <= document_columns
    assert {"document_id", "content", "content_hash", "embedding"} <= chunk_columns
    assert {"query_summary", "hit_document_ids", "user_id"} <= query_log_columns
    assert {"raw_query", "api_key", "prompt", "ocr_text"}.isdisjoint(query_log_columns)


def test_explicit_migration_matches_rag_model_columns():
    from app.rag.models import RagChunk, RagDocument, RagQueryLog

    sql = MIGRATION.read_text(encoding="utf-8").lower()
    for model in (RagDocument, RagChunk, RagQueryLog):
        assert f"create table if not exists {model.__tablename__}" in sql
        for column in model.__table__.columns.keys():
            assert column.lower() in sql


def test_application_startup_does_not_silently_create_rag_tables(monkeypatch):
    from app import main

    calls = []
    monkeypatch.setattr(main.Base.metadata, "create_all", lambda **kwargs: calls.append(kwargs))

    main.init_db()

    table_names = {table.name for table in calls[0]["tables"]}
    assert {"rag_documents", "rag_chunks", "rag_query_logs"}.isdisjoint(table_names)


def test_rag_chunk_embedding_round_trips_a_512_dimension_vector():
    from app.rag.models import RagChunk, RagDocument

    engine = create_engine("sqlite://")
    RagDocument.metadata.create_all(engine, tables=[RagDocument.__table__, RagChunk.__table__])
    Session = sessionmaker(bind=engine)

    with Session.begin() as session:
        document = RagDocument(
            source_uri="policy://refund/v1",
            source_hash="a" * 64,
            version="v1",
            access_scope="supervisor",
        )
        session.add(document)
        session.flush()
        session.add(
            RagChunk(
                document_id=document.id,
                chunk_index=0,
                content="退款政策",
                content_hash="b" * 64,
                embedding=[0.1] * 512,
            )
        )

    with Session() as session:
        stored = session.query(RagChunk).one()
        assert stored.embedding == [0.1] * 512


@pytest.mark.parametrize("dimension", [511, 513])
def test_rag_chunk_embedding_rejects_wrong_dimension(dimension):
    from app.rag.models import Vector512

    processor = Vector512().bind_processor(None)

    with pytest.raises(ValueError, match="512"):
        processor([0.1] * dimension)


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), "1.0"])
def test_rag_chunk_embedding_rejects_non_finite_or_non_numeric_values(invalid_value):
    from app.rag.models import Vector512

    processor = Vector512().bind_processor(None)

    with pytest.raises(ValueError, match="数值"):
        processor([invalid_value] + [0.1] * 511)
