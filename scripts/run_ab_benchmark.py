"""A/B 成本对比：纯 LLM 路由 vs 双层混合流（工单 8 任务三）。

对 evals/intent/intent_samples.jsonl 全部样本：
- 纯 LLM：每条样本都执行 fraud+sentiment 两次 LLM 调用；
- 双层混合流：Node A 命中强信号直接跳过 LLM，其余走 LLM。
输出 docs/evidence/ab-benchmark-report.md 与 Token 降低率（目标 ≥40%）。
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.intent import IntentFilter  # noqa: E402
from app.agents.llm import (  # noqa: E402
    LlmRiskClient,
    score_risk_parallel_with_usage,
    score_risk_parallel_with_usage_and_fallbacks,
)
from app.config import settings  # noqa: E402
from evals.schemas import load_intent_samples  # noqa: E402

_REFUND_KEYWORDS = ("退款", "退货", "退钱", "退换", "退回", "退赔", "赔偿", "赔付")


def _predict_label(text: str, fraud_score: int, sentiment: str) -> str:
    if fraud_score >= settings.FRAUD_SCORE_THRESHOLD:
        return "malicious"
    if sentiment == "HIGH":
        return "complaint"
    if any(keyword in text for keyword in _REFUND_KEYWORDS):
        return "refund_request"
    return "general"


def _run_pure_llm(text: str) -> tuple[int, float, str]:
    """纯 LLM：两条调用都执行，返回 (tokens, ttft_ms, 预测标签)。"""
    client = LlmRiskClient()
    material = f"退款金额：128\n凭证 OCR：{text}"
    started_at = time.perf_counter()
    fraud, sentiment, fraud_usage, sentiment_usage, _, _ = asyncio.run(
        score_risk_parallel_with_usage(client, material)
    )
    ttft_ms = (time.perf_counter() - started_at) * 1000
    tokens = fraud_usage.total_tokens + sentiment_usage.total_tokens
    return tokens, ttft_ms, _predict_label(text, int(fraud), str(sentiment))


def _run_two_layer(text: str) -> tuple[int, float, str, str]:
    """双层混合流：强信号跳过 LLM，返回 (tokens, ttft_ms, 预测标签, 分流)。"""
    result = IntentFilter().classify(text)
    if result.route == "strong_signal":
        return 0, 0.0, result.label, "strong_signal"
    client = LlmRiskClient()
    material = f"退款金额：128\n凭证 OCR：{text}"
    started_at = time.perf_counter()
    fraud, sentiment, fraud_usage, sentiment_usage, _, _, _ = asyncio.run(
        score_risk_parallel_with_usage_and_fallbacks(client, material)
    )
    ttft_ms = (time.perf_counter() - started_at) * 1000
    tokens = fraud_usage.total_tokens + sentiment_usage.total_tokens
    return tokens, ttft_ms, _predict_label(text, int(fraud), str(sentiment)), "llm_judge"


def run_ab_benchmark() -> dict:
    samples = load_intent_samples(ROOT / "evals" / "intent" / "intent_samples.jsonl")
    pure_tokens = 0
    hybrid_tokens = 0
    pure_ttft_sum = 0.0
    hybrid_ttft_sum = 0.0
    pure_correct = 0
    hybrid_correct = 0
    skipped = 0
    rows = []
    for sample in samples:
        pure_tokens_s, pure_ttft, pure_label = _run_pure_llm(sample.text)
        hybrid_tokens_s, hybrid_ttft, hybrid_label, route = _run_two_layer(sample.text)
        pure_tokens += pure_tokens_s
        hybrid_tokens += hybrid_tokens_s
        pure_ttft_sum += pure_ttft
        hybrid_ttft_sum += hybrid_ttft
        pure_correct += int(pure_label == sample.expected_label)
        hybrid_correct += int(hybrid_label == sample.expected_label)
        skipped += int(route == "strong_signal")
        rows.append(
            {
                "case_id": sample.case_id,
                "expected": sample.expected_label,
                "pure_label": pure_label,
                "hybrid_label": hybrid_label,
                "route": route,
            }
        )
    count = len(samples)
    token_reduction = (pure_tokens - hybrid_tokens) / pure_tokens if pure_tokens else 0.0
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": settings.LLM_PROVIDER,
        "measurement_type": "actual" if settings.LLM_PROVIDER != "mock" else "estimated",
        "sample_count": count,
        "pure_llm": {
            "total_tokens": pure_tokens,
            "avg_ttft_ms": round(pure_ttft_sum / count, 2) if count else 0.0,
            "accuracy": round(pure_correct / count, 4) if count else 0.0,
        },
        "two_layer": {
            "total_tokens": hybrid_tokens,
            "avg_ttft_ms": round(hybrid_ttft_sum / count, 2) if count else 0.0,
            "accuracy": round(hybrid_correct / count, 4) if count else 0.0,
            "strong_signal_skipped": skipped,
        },
        "token_reduction": round(token_reduction, 4),
        "passed": token_reduction >= 0.40,
    }
    _write_report(report, rows)
    return report


def _write_report(report: dict, rows: list[dict]) -> None:
    out = ROOT / "docs" / "evidence" / "ab-benchmark-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    pure = report["pure_llm"]
    hybrid = report["two_layer"]
    lines = [
        "# A/B 成本对比报告（纯 LLM vs 双层混合流）",
        "",
        f"- 时间：{report['generated_at']}，provider：{report['provider']}，"
        f"measurement：{report['measurement_type']}",
        f"- 样本数：{report['sample_count']}",
        "",
        "| 方案 | Token 消耗 | 平均 TTFT(ms) | 意图准确率 |",
        "| --- | --- | --- | --- |",
        f"| 纯 LLM | {pure['total_tokens']} | {pure['avg_ttft_ms']} | {pure['accuracy']:.1%} |",
        f"| 双层混合流 | {hybrid['total_tokens']} | {hybrid['avg_ttft_ms']} | {hybrid['accuracy']:.1%} |",
        "",
        f"- Token 降低率：{report['token_reduction']:.1%}（目标 ≥40%，结果：{'达标' if report['passed'] else '未达标'}）",
        f"- 强信号跳过 LLM 样本数：{hybrid['strong_signal_skipped']}",
        "",
        "## 样本明细",
        "",
        "| case_id | 期望意图 | 纯 LLM 预测 | 双层预测 | 分流 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['expected']} | {row['pure_label']} | "
            f"{row['hybrid_label']} | {row['route']} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    result = run_ab_benchmark()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
