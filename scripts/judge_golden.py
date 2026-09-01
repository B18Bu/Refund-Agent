"""LLM-as-a-judge 评测入口：对 10 条 Golden Dataset 运行评审并落报告。

依赖：LLM_PROVIDER=deepseek 时调用真实模型评审；mock 时 judge 明确跳过（status=SKIPPED），
确定性规则评测仍照常运行并作为唯一事实来源。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.decision_rules import decide  # noqa: E402
from app.config import settings  # noqa: E402
from app.evaluation.judge import judge_case  # noqa: E402
from evals.schemas import load_golden_cases  # noqa: E402


def run() -> dict:
    cases = load_golden_cases(ROOT / "evals" / "golden" / "refund_cases.jsonl")
    results = []
    for case in cases:
        payload = {
            "case_id": case.case_id,
            "amount": case.amount,
            "ocr_confidence": case.ocr_confidence,
            "fraud_score": case.fraud_score,
            "sentiment": case.sentiment,
            "expected_route": case.expected_route,
            "expected_reasons": case.expected_reasons,
        }
        actual = decide(case.amount, case.ocr_confidence, case.fraud_score, case.sentiment)
        judge = judge_case(payload, actual)
        results.append(
            {
                "case_id": case.case_id,
                "actual_route": actual,
                "expected_route": case.expected_route,
                "correct": actual == case.expected_route,
                "judge": judge,
                "judge_status": "JUDGED" if judge is not None else "SKIPPED",
            }
        )
    judged = sum(1 for item in results if item["judge_status"] == "JUDGED")
    return {
        "judge_provider": settings.LLM_PROVIDER,
        "case_count": len(results),
        "judged": judged,
        "skipped": len(results) - judged,
        "results": results,
    }


if __name__ == "__main__":
    report = run()
    output = ROOT / "artifacts" / "golden-judge-report.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if all(item["correct"] for item in report["results"]) else 1)
