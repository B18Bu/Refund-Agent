"""沙箱文件路径策略。"""
from __future__ import annotations

import os
from pathlib import Path


def validate_path(path: str | Path, root: str | Path) -> Path:
    """解析路径并确保它位于 root 内；拒绝遍历和符号链接逃逸。"""
    root_path = Path(root).resolve(strict=False)
    candidate = Path(path).resolve(strict=False)
    try:
        candidate.relative_to(root_path)
    except ValueError as exc:
        raise ValueError("沙箱路径超出任务根目录") from exc
    if os.path.islink(path):
        raise ValueError("沙箱不允许符号链接输入")
    return candidate

