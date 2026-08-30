"""沙箱适配器的最小契约。"""
from __future__ import annotations

from dataclasses import dataclass


class SandboxUnavailable(RuntimeError):
    """当前环境未配置可用的隔离沙箱。"""


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""


class SandboxAdapter:
    def execute(self, argv: list[str], input_dir: str, output_dir: str) -> SandboxResult:
        raise NotImplementedError

    def destroy(self) -> None:
        raise NotImplementedError

