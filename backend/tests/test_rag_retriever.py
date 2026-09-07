from app.rag.models import RagChunk, RagDocument


def _vector(first: float) -> list[float]:
    return [first] + [0.0] * 511


def test_retriever_returns_only_supervisor_chunks_above_threshold(db_session):
    from app.rag.retriever import RagRetriever

    allowed = RagDocument(
        source_uri="docs/guides/refund.md",
        source_hash="a" * 64,
        version="v1",
        access_scope="supervisor",
        title="退款规范",
    )
    hidden = RagDocument(
        source_uri="docs/evidence/internal.md",
        source_hash="b" * 64,
        version="v2",
        access_scope="internal",
        title="内部资料",
    )
    db_session.add_all([allowed, hidden])
    db_session.flush()
    db_session.add_all([
        RagChunk(document_id=allowed.id, chunk_index=0, content="128 元低风险退款规则", content_hash="c" * 64, embedding=_vector(1.0)),
        RagChunk(document_id=hidden.id, chunk_index=0, content="不得返回", content_hash="d" * 64, embedding=_vector(1.0)),
    ])
    db_session.commit()

    results = RagRetriever(db_session, minimum_similarity=0.8).search(_vector(1.0))

    assert len(results) == 1
    assert results[0].source == "docs/guides/refund.md"
    assert results[0].section == "退款规范"
    assert results[0].version == "v1"
    assert results[0].similarity == 1.0


def test_retriever_returns_empty_when_all_matches_are_below_threshold(db_session):
    from app.rag.retriever import RagRetriever

    document = RagDocument(source_uri="docs/guides/refund.md", source_hash="e" * 64, version="v1", access_scope="supervisor")
    db_session.add(document)
    db_session.flush()
    db_session.add(RagChunk(document_id=document.id, chunk_index=0, content="退款规则", content_hash="f" * 64, embedding=_vector(0.0)))
    db_session.commit()

    assert RagRetriever(db_session, minimum_similarity=0.8).search(_vector(1.0)) == []


def test_postgres_query_binds_embedding_and_caps_limit_at_five():
    from app.rag.retriever import RagRetriever

    captured = {}

    class Result:
        def mappings(self):
            return []

    class Session:
        def execute(self, statement, params):
            captured["sql"] = str(statement)
            captured["params"] = params
            return Result()

    retriever = RagRetriever(Session(), limit=99)

    assert retriever._postgres_search(_vector(1.0)) == []
    assert ":embedding" in captured["sql"]
    assert captured["params"]["embedding"].startswith("[")
    assert captured["params"]["limit"] == 5
