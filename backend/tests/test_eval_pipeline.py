"""工单 8 评测管线测试：30 条口语样本、Fallback 原因、重试退避、runner 指标、DLQ。"""
import pytest
from types import SimpleNamespace


SAMPLE_CASES = [
    # ---- 强信号：恶意/黑产（strong_signal）----
    {"case_id": "I01", "text": "这批订单都是刷单的，给我全部退款不掉货", "expected_label": "malicious", "expected_route": "strong_signal"},
    {"case_id": "I02", "text": "恶意套现，用假订单申请赔付", "expected_label": "malicious", "expected_route": "strong_signal"},
    {"case_id": "I03", "text": "黑产团伙批量下单，现在要求退款", "expected_label": "malicious", "expected_route": "strong_signal"},
    {"case_id": "I04", "text": "这就是薅羊毛，必须给我赔", "expected_label": "malicious", "expected_route": "strong_signal"},
    {"case_id": "I05", "text": "伪造凭证，凭证图片是 P 的", "expected_label": "malicious", "expected_route": "strong_signal"},
    {"case_id": "I06", "text": "洗钱订单，要求立即退款", "expected_label": "malicious", "expected_route": "strong_signal"},
    {"case_id": "I07", "text": "虚构订单号来骗赔偿，恶意投诉", "expected_label": "malicious", "expected_route": "strong_signal"},
    {"case_id": "I08", "text": "假图 PS 的凭证，套现退款", "expected_label": "malicious", "expected_route": "strong_signal"},
    # ---- 退款申请（llm_judge）----
    {"case_id": "I09", "text": "我买的东西坏了，能不能给我退钱", "expected_label": "refund_request", "expected_route": "llm_judge"},
    {"case_id": "I10", "text": "商品和描述完全不一样，我要退货", "expected_label": "refund_request", "expected_route": "llm_judge"},
    {"case_id": "I11", "text": "东西收到就碎了，申请全额退款", "expected_label": "refund_request", "expected_route": "llm_judge"},
    {"case_id": "I12", "text": "漏发了一件，退钱给我", "expected_label": "refund_request", "expected_route": "llm_judge"},
    {"case_id": "I13", "text": "尺寸不合适，我要退货退款", "expected_label": "refund_request", "expected_route": "llm_judge"},
    {"case_id": "I14", "text": "客服说过期可以退，现在不认账，请退款", "expected_label": "refund_request", "expected_route": "llm_judge"},
    {"case_id": "I15", "text": "这个月第二次出问题了，麻烦退款吧", "expected_label": "refund_request", "expected_route": "llm_judge"},
    {"case_id": "I16", "text": "订单号 800124 金额 128 元，申请退赔", "expected_label": "refund_request", "expected_route": "llm_judge"},
    # ---- 投诉（llm_judge）----
    {"case_id": "I17", "text": "我要投诉你们，态度太差了", "expected_label": "complaint", "expected_route": "llm_judge"},
    {"case_id": "I18", "text": "再不给解决我就去曝光你们", "expected_label": "complaint", "expected_route": "llm_judge"},
    {"case_id": "I19", "text": "气死我了，维权到底", "expected_label": "complaint", "expected_route": "llm_judge"},
    {"case_id": "I20", "text": "已经在黑猫投诉了，等你们答复", "expected_label": "complaint", "expected_route": "llm_judge"},
    {"case_id": "I21", "text": "愤怒，客服一直不回复", "expected_label": "complaint", "expected_route": "llm_judge"},
    {"case_id": "I22", "text": "我要曝光你们虚假宣传", "expected_label": "complaint", "expected_route": "llm_judge"},
    # ---- 一般咨询/其他（llm_judge）----
    {"case_id": "I23", "text": "你好，请问怎么查我的订单进度", "expected_label": "general", "expected_route": "llm_judge"},
    {"case_id": "I24", "text": "物流显示已签收但我没收到", "expected_label": "general", "expected_route": "llm_judge"},
    {"case_id": "I25", "text": "想了解一下七天无理由退换规则", "expected_label": "refund_request", "expected_route": "llm_judge"},
    {"case_id": "I26", "text": "发票什么时候能开", "expected_label": "general", "expected_route": "llm_judge"},
    {"case_id": "I27", "text": "客服电话打不通，在线等", "expected_label": "general", "expected_route": "llm_judge"},
    {"case_id": "I28", "text": "能不能帮我查一下优惠券到账没有", "expected_label": "general", "expected_route": "llm_judge"},
    {"case_id": "I29", "text": "换个收货地址怎么操作", "expected_label": "general", "expected_route": "llm_judge"},
    {"case_id": "I30", "text": "订单取消后钱多久能退回来", "expected_label": "refund_request", "expected_route": "llm_judge"},
]


def test_eval_pipeline_30_colloquial_samples():
    from app.agents.intent import IntentFilter

    intent_filter = IntentFilter()
    mismatches = []
    for case in SAMPLE_CASES:
        result = intent_filter.classify(case["text"])
        if result.route != case["expected_route"]:
            mismatches.append(f"{case['case_id']} route={result.route}")
        elif result.label != case["expected_label"]:
            mismatches.append(f"{case['case_id']} label={result.label}")
    assert mismatches == []


def test_json_parse_fallback_records_reason(monkeypatch):
    from app.agents import llm

    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))],
        usage=SimpleNamespace(prompt_tokens=40, completion_tokens=2, total_tokens=42),
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response))
    )
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(llm, "get_client", lambda: fake_client)

    value, usage, reason = llm.LlmRiskClient().score_fraud_with_usage_and_reason("材料")

    assert value == 100
    assert reason == "llm_output_parse_fallback"
    assert usage.measurement_type == "actual"


def test_retry_backoff_retries_then_falls_back(monkeypatch):
    from app.agents import llm

    calls = {"n": 0}

    def flaky(**_kwargs):
        calls["n"] += 1
        raise RuntimeError("network down")

    monkeypatch.setattr(llm.settings, "LLM_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(llm.settings, "LLM_RETRY_BASE_DELAY_SECONDS", 0.0)

    with pytest.raises(RuntimeError):
        llm.retry_call(flaky, attempts=3, base_delay=0.0)
    assert calls["n"] == 3

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=flaky))
    )
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(llm, "get_client", lambda: fake_client)

    value, _, reason = llm.LlmRiskClient().score_fraud_with_usage_and_reason("材料")

    assert value == 100
    assert reason == "llm_call_failed"
    assert calls["n"] == 6


def test_eval_runner_metric():
    from app.evaluation.runner import run_periodic_eval

    report = run_periodic_eval()

    assert report["coverage"] == 1.0
    for key in ("intent_recall", "hallucination_rate", "coverage", "avg_ttft_ms", "total_tokens"):
        assert key in report
        assert report[key] is not None


def test_worker_dlq_on_final_failure(monkeypatch, redis_client):
    from app.worker import consumer

    redis_client.xadd("stream:tickets", {
        "ticket_id": "999",
        "thread_id": "thread-dlq",
        "trace_id": "trace-dlq-1",
        "type": "START",
    })
    monkeypatch.setattr(consumer, "get_redis", lambda: redis_client)
    monkeypatch.setattr(
        consumer,
        "process",
        lambda _fields: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(consumer, "emit_refund_trace", lambda **_kwargs: None)
    monkeypatch.setattr(consumer, "mark_failed", lambda *_args, **_kwargs: None)

    processed = consumer.run_once()

    assert processed == 1
    dead = redis_client.xrange("stream:tickets:dead", count=10)
    assert dead
    fields = dict(dead[0][1])
    assert fields["ticket_id"] == "999"
    assert fields["trace_id"] == "trace-dlq-1"
    assert fields["error_code"] == consumer.ERR_PROCESS_FAILED
