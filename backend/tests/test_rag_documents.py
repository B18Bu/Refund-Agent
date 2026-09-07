import app.models  # noqa: F401 - 在 SQLite 测试建表前注册既有外键目标。

from pathlib import Path

import pytest


class FakeEmbeddingClient:
    dimension = 512

    def embed(self, texts):
        return [[0.1] * self.dimension for _ in texts]


def test_document_scanner_reads_only_fixed_whitelist(tmp_path):
    from app.rag.documents import scan_whitelisted_documents

    allowed = tmp_path / "docs" / "specs" / "policy.md"
    allowed.parent.mkdir(parents=True)
    allowed.write_text("退款政策", encoding="utf-8")
    denied = tmp_path / "docs" / "private" / "secret.md"
    denied.parent.mkdir(parents=True)
    denied.write_text("不得索引", encoding="utf-8")

    documents = scan_whitelisted_documents(tmp_path)

    assert [document.source_uri for document in documents] == ["docs/specs/policy.md"]


@pytest.mark.parametrize(
    ("relative_path", "symlinked_path"),
    [
        (Path("docs/specs/policy.md"), Path("docs/specs")),
        (Path("backend/app/security/auth.py"), Path("backend/app/security")),
        (
            Path("backend/app/agents/decision_rules.py"),
            Path("backend/app/agents/decision_rules.py"),
        ),
        (Path("docs/specs/policy.md"), Path("docs")),
        (Path("docs/specs/policy.md"), Path("docs/specs/policy.md")),
    ],
)
def test_document_scanner_rejects_all_symlinked_whitelist_path_components(
    tmp_path, monkeypatch, relative_path, symlinked_path
):
    from app.rag.documents import scan_whitelisted_documents

    policy = tmp_path / relative_path
    policy.parent.mkdir(parents=True)
    policy.write_text("退款政策", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == tmp_path / symlinked_path,
    )

    assert scan_whitelisted_documents(tmp_path) == []


def test_document_scanner_skips_invalid_utf8_file_and_continues_batch(tmp_path):
    from app.rag.documents import scan_whitelisted_documents

    readable = tmp_path / "docs" / "specs" / "policy.md"
    unreadable = tmp_path / "docs" / "specs" / "broken.txt"
    readable.parent.mkdir(parents=True)
    readable.write_text("退款政策", encoding="utf-8")
    unreadable.write_bytes(b"\xff\xfe")

    documents = scan_whitelisted_documents(tmp_path)

    assert [document.source_uri for document in documents] == ["docs/specs/policy.md"]


def test_indexer_masks_sensitive_text_and_is_idempotent(db_session, tmp_path):
    from app.rag.indexer import RagIndexer
    from app.rag.models import RagChunk, RagDocument

    source = tmp_path / "docs" / "guides" / "policy.md"
    source.parent.mkdir(parents=True)
    source.write_text("联系 13800000000 后按退款政策处理。", encoding="utf-8")
    indexer = RagIndexer(db_session, FakeEmbeddingClient(), repository_root=tmp_path)

    first_run = indexer.index()
    db_session.commit()
    second_run = indexer.index()

    chunk = db_session.query(RagChunk).one()
    assert first_run.created_documents == 1
    assert first_run.created_chunks == 1
    assert second_run.created_documents == 0
    assert second_run.created_chunks == 0
    assert db_session.query(RagDocument).count() == 1
    assert "13800000000" not in chunk.content
    assert "138****0000" in chunk.content
