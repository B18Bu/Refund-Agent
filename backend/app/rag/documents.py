"""RAG 可索引资料的固定白名单。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_WHITELIST_DIRECTORIES = (
    Path("docs/specs"),
    Path("docs/guides"),
    Path("docs/evidence"),
    Path("specs/001-refund-decision-mvp"),
    Path("evals/golden"),
    Path("backend/app/security"),
)
_WHITELIST_FILES = (Path("backend/app/agents/decision_rules.py"),)
_TEXT_EXTENSIONS = {".md", ".py", ".jsonl", ".txt"}


@dataclass(frozen=True)
class SourceDocument:
    source_uri: str
    content: str
    title: str


def _has_symlink_in_ancestor_chain(path: Path, root: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        if current == root:
            return False
        current = current.parent


def scan_whitelisted_documents(repository_root: Path) -> list[SourceDocument]:
    """读取批准来源，忽略缺失目录、二进制文件和所有非白名单路径。"""
    root = repository_root.resolve()
    files: list[Path] = []
    for relative in _WHITELIST_DIRECTORIES:
        directory = root / relative
        if not _has_symlink_in_ancestor_chain(directory, root) and directory.is_dir():
            files.extend(path for path in directory.rglob("*") if path.is_file())
    for relative in _WHITELIST_FILES:
        path = root / relative
        if not _has_symlink_in_ancestor_chain(path, root) and path.is_file():
            files.append(path)

    documents: list[SourceDocument] = []
    for path in sorted(set(files)):
        if _has_symlink_in_ancestor_chain(path, root):
            continue
        resolved = path.resolve()
        if path.suffix.lower() not in _TEXT_EXTENSIONS or not resolved.is_relative_to(root):
            continue
        try:
            content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        relative = resolved.relative_to(root).as_posix()
        documents.append(SourceDocument(relative, content, resolved.name))
    return documents
