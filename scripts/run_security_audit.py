"""生成静态安全审计摘要，不执行被审计代码。"""
from __future__ import annotations

import json
import io
import re
import tokenize
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHELL_TRUE = re.compile(r"\bshell\s*=\s*True\b")
REDIS_EVAL = re.compile(r"\.eval\s*\(")


def _executable_source(source: str) -> str:
    """移除注释与字符串，避免把说明文字误报为可执行调用。"""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        return "".join(
            token.string
            for token in tokens
            if token.type not in (tokenize.COMMENT, tokenize.STRING)
        )
    except tokenize.TokenError:
        return source


def run() -> dict:
    finding_counts = {"shell_true": 0, "reviewed_redis_eval": 0}
    for path in [*ROOT.joinpath("backend").rglob("*.py"), *ROOT.joinpath("scripts").rglob("*.py")]:
        source = _executable_source(path.read_text(encoding="utf-8"))
        finding_counts["shell_true"] += len(SHELL_TRUE.findall(source))
        finding_counts["reviewed_redis_eval"] += len(REDIS_EVAL.findall(source))
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "passed" if finding_counts["shell_true"] == 0 else "needs_review",
        "finding_counts": finding_counts,
    }
    output = ROOT / "artifacts" / "security-audit-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
