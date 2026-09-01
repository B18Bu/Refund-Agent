"""工单 8 周期评测 runner：Golden + 安全网关 + 意图样本，输出指标报告。

入口：
    python -m app.evaluation.runner            （backend 目录下）
    scripts/schedule_periodic_eval.py --run-now

指标口径见 docs/workorder8-intent-orchestration-tech-spec.md 第 5 节：
intent_recall（主意图 refund_request）≥90%、hallucination_rate ≤2%、coverage=100%。
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.decision_rules import decide  # noqa: E402
from app.agents.intent import IntentFilter  # noqa: E402
from app.agents.llm import LlmRiskClient, get_client, score_risk_parallel_with_usage_and_fallbacks  # noqa: E402
from app.config import settings  # noqa: E402
from app.security.gateway import CriticEngine  # noqa: E402
from evals.schemas import load_golden_cases, load_intent_samples  # noqa: E402

_REFUND_KEYWORDS = ("退款", "退货", "退钱", "退换", "退回", "退赔", "赔偿", "赔付")


def _predict_label(text: str, fraud_score: int, sentiment: str) -> str:
    """LLM 输出到意图标签的确定性映射（非模型判断）。"""
    if fraud_score >= settings.FRAUD_SCORE_THRESHOLD:
        return "malicious"
    if sentiment == "HIGH":
        return "complaint"
    if any(keyword in text for keyword in _REFUND_KEYWORDS):
        return "refund_request"
    return "general"


def _classify_intent_sample(text: str) -> dict:
    """双层流：Node A 强信号直判；llm_judge 走 LLM 并行分析后确定性映射标签。"""
    result = IntentFilter().classify(text)
    if result.route == "strong_signal":
        return {
            "label": result.label,
            "route": "strong_signal",
            "fallback_reasons": [],
            "tokens": 0,
            "ttft_ms": 0.0,
        }
    client = LlmRiskClient()
    material = f"退款金额：128\n凭证 OCR：{text}"
    started_at = time.perf_counter()
    fraud, sentiment, fraud_usage, sentiment_usage, _, _, fallback_reasons = asyncio.run(
        score_risk_parallel_with_usage_and_fallbacks(client, material)
    )
    ttft_ms = (time.perf_counter() - started_at) * 1000
    return {
        "label": _predict_label(text, int(fraud), str(sentiment)),
        "route": "llm_judge",
        "fallback_reasons": list(dict.fromkeys(fallback_reasons)),
        "tokens": fraud_usage.total_tokens + sentiment_usage.total_tokens,
        "ttft_ms": ttft_ms,
    }


def _judge_hallucination(text: str, predicted: str, expected: str) -> tuple[bool, str]:
    """返回 (是否幻觉, 判定方式)。deepseek 用 LLM-as-a-judge；mock 用确定性代理。"""
    if settings.LLM_PROVIDER != "mock":
        client = get_client()
        if client is not None:
            prompt = (
                f"用户材料：{text}\n预测意图：{predicted}\n标注意图：{expected}\n"
                "判断预测是否构成幻觉（输出与材料冲突且材料中无依据），"
                '只输出 JSON：{"hallucinated": true 或 false}'
            )
            try:
                resp = client.chat.completions.create(
                    model=settings.DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": "你是评测评审专家，只输出 JSON。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    timeout=30,
                )
                data = json.loads(resp.choices[0].message.content or "{}")
                return bool(data.get("hallucinated", False)), "JUDGED"
            except Exception:
                pass
    return predicted != expected, "PROXY"


def _write_report_md(report: dict) -> None:
    """按日期追加周期评测报告到 docs/evidence/periodic-eval-report.md。"""
    out = ROOT / "docs" / "evidence" / "periodic-eval-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    intent = report["intent"]
    section = (
        f"## {report['generated_at']}（provider={report['provider']}）\n\n"
        f"- Golden：{report['golden']['passed']}（{report['golden']['case_count']} 条）\n"
        f"- 安全网关：拦截率 {report['security']['block_rate']:.1%}（{report['security']['sample_count']} 条）\n"
        f"- 意图：样本 {intent['sample_count']} 条，覆盖率 {intent['coverage']:.1%}，"
        f"召回率 {intent['intent_recall']:.1%}，幻觉率 {intent['hallucination_rate']:.2%}，"
        f"TTFT {intent['avg_ttft_ms']:.0f}ms，Token {intent['total_tokens']}\n"
        f"- 结论：{report['passed']}\n"
    )
    existing = out.read_text(encoding="utf-8") if out.exists() else ""
    out.write_text(existing + section, encoding="utf-8")


def run_periodic_eval() -> dict:
    golden_cases = load_golden_cases(ROOT / "evals" / "golden" / "refund_cases.jsonl")
    golden_results = []
    for case in golden_cases:
        actual = decide(case.amount, case.ocr_confidence, case.fraud_score, case.sentiment)
        golden_results.append(
            {
                "case_id": case.case_id,
                "actual": actual,
                "expected": case.expected_route,
                "correct": actual == case.expected_route,
            }
        )
    golden_passed = (
        len(golden_results) == 10 and all(item["correct"] for item in golden_results)
    )

    security_blocked = 0
    security_total = 0
    security_path = ROOT / "evals" / "security" / "injection_payloads.jsonl"
    if security_path.exists():
        for line in security_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            risk, _rules = CriticEngine().score(str(payload.get("text", "")))
            security_blocked += int(risk >= settings.SECURITY_INJECTION_THRESHOLD)
            security_total += 1

    samples = load_intent_samples(ROOT / "evals" / "intent" / "intent_samples.jsonl")
    intent_results = []
    total_tokens = 0
    ttft_sum = 0.0
    hallucinated = 0
    judge_statuses = set()
    for sample in samples:
        outcome = _classify_intent_sample(sample.text)
        total_tokens += outcome["tokens"]
        ttft_sum += outcome["ttft_ms"]
        correct = outcome["label"] == sample.expected_label
        hallucinated_flag, judge_status = _judge_hallucination(
            sample.text, outcome["label"], sample.expected_label
        )
        judge_statuses.add(judge_status)
        hallucinated += int(hallucinated_flag)
        intent_results.append(
            {
                "case_id": sample.case_id,
                "predicted": outcome["label"],
                "expected": sample.expected_label,
                "route": outcome["route"],
                "correct": correct,
                "fallback_reasons": outcome["fallback_reasons"],
                "judge_status": judge_status,
            }
        )

    refund_correct = sum(
        1
        for item in intent_results
        if item["expected"] == "refund_request" and item["predicted"] == "refund_request"
    )
    refund_total = sum(1 for item in intent_results if item["expected"] == "refund_request")
    sample_count = len(intent_results)
    intent_recall = refund_correct / refund_total if refund_total else 0.0
    hallucination_rate = hallucinated / sample_count if sample_count else 0.0
    coverage = sample_count / len(samples) if samples else 0.0
    avg_ttft_ms = ttft_sum / sample_count if sample_count else 0.0
    passed = (
        golden_passed
        and coverage == 1.0
        and intent_recall >= 0.90
        and hallucination_rate <= 0.02
    )
    intent_metrics = {
        "sample_count": sample_count,
        "coverage": round(coverage, 4),
        "intent_recall": round(intent_recall, 4),
        "hallucination_rate": round(hallucination_rate, 4),
        "avg_ttft_ms": round(avg_ttft_ms, 2),
        "total_tokens": total_tokens,
        "judge_status": "JUDGED" if "JUDGED" in judge_statuses else "PROXY",
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": settings.LLM_PROVIDER,
        "golden": {"case_count": len(golden_results), "passed": golden_passed},
        "security": {
            "sample_count": security_total,
            "block_rate": round(security_blocked / security_total, 4) if security_total else 0.0,
        },
        **intent_metrics,
        "intent": intent_metrics,
        "passed": passed,
    }
    _write_report_md(report)
    return report


if __name__ == "__main__":
    result = run_periodic_eval()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
