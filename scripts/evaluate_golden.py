"""运行确定性退赔 Golden Dataset，输出可审计 JSON 报告。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.decision_rules import decide  # noqa: E402
from evals.schemas import load_golden_cases  # noqa: E402


def evaluate() -> dict:
    cases = load_golden_cases(ROOT / "evals" / "golden" / "refund_cases.jsonl")
    results = []
    for case in cases:
        actual = decide(case.amount, case.ocr_confidence, case.fraud_score, case.sentiment)
        correct = actual == case.expected_route
        safe = case.security_expectation == "ALLOW_AUTO" or actual == "HUMAN_REVIEW"
        explainable = bool(case.expected_reasons)
        results.append({"case_id": case.case_id, "actual_route": actual, "expected_route": case.expected_route, "correct": correct, "safe": safe, "explainable": explainable})
    score = sum(int(item[key]) for item in results for key in ("correct", "safe", "explainable"))
    return {"case_count": len(results), "score": score, "max_score": len(results) * 3, "passed": all(item["correct"] and item["safe"] and item["explainable"] for item in results), "results": results}


if __name__ == "__main__":
    report = evaluate()
    output = ROOT / "artifacts" / "golden-report.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)
