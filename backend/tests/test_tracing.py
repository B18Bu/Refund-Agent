import threading


def test_trace_payload_redacts_secrets_and_raw_material():
    from app.observability.tracing import sanitize_payload

    result = sanitize_payload({"trace_id": "t1", "api_key": "secret", "authorization": "Bearer x", "ocr_text": "敏感原文", "latency_ms": 12})

    assert result["trace_id"] == "t1"
    assert result["latency_ms"] == 12
    assert "api_key" not in result
    assert "authorization" not in result
    assert "ocr_text" not in result


def test_telemetry_queue_is_non_blocking_when_full():
    from app.observability.queue import TelemetryQueue

    started = threading.Event()
    release = threading.Event()

    def exporter(_):
        started.set()
        release.wait(timeout=1)

    queue = TelemetryQueue(maxsize=1, exporter=exporter, autostart=False)
    try:
        assert queue.emit({"event": 1}) is True
        queue.start()
        assert started.wait(timeout=1)
        assert queue.emit({"event": 2}) is True
        assert queue.emit({"event": 3}) is False
    finally:
        release.set()
        queue.close(timeout=1)


def test_trace_context_generates_and_preserves_trace_id():
    from app.observability.tracing import TraceContext

    generated = TraceContext.ensure(None, ticket_id=12)
    preserved = TraceContext.ensure(generated.trace_id, ticket_id=12)

    assert generated.trace_id
    assert preserved.trace_id == generated.trace_id
    assert preserved.ticket_id == 12


def test_langfuse_emit_queues_sanitized_trace(monkeypatch):
    from app.observability import langfuse

    posted = []

    def fake_post(payload):
        posted.append(payload)

    monkeypatch.setattr(langfuse.settings, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(langfuse.settings, "TELEMETRY_PROVIDER", "langfuse")
    monkeypatch.setattr(langfuse.settings, "LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setattr(langfuse.settings, "LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setattr(langfuse, "_post", fake_post)
    monkeypatch.setattr(langfuse, "_queue", None)

    ok = langfuse.emit_refund_trace(
        trace_id="t-1",
        ticket_id=7,
        spans=[
            {"name": "OCR", "status": "SUCCESS", "output": {"summary": "x", "ocr_text": "敏感原文"}},
            {"name": "Decision", "status": "SUCCESS", "output": {"summary": "AUTO_REFUND: ocr_amount_match"}},
        ],
        final_decision="AUTO_REFUNDED",
    )

    assert ok is True
    queue = langfuse.get_queue()
    try:
        queue.close(timeout=1)
    except Exception:
        pass
    assert len(posted) == 1
    payload = posted[0]
    events = payload["batch"]
    assert events[0]["type"] == "trace-create"
    assert events[0]["body"]["id"] == "t-1"
    assert events[0]["body"]["metadata"]["ticket_id"] == "7"
    span_events = [e for e in events if e["type"] == "span-create"]
    assert len(span_events) == 2
    ocr_span = span_events[0]["body"]
    assert ocr_span["traceId"] == "t-1"
    assert "ocr_text" not in ocr_span["output"]
    assert ocr_span["output"]["summary"] == "x"


def test_langfuse_disabled_or_misconfigured_returns_false(monkeypatch):
    from app.observability import langfuse

    monkeypatch.setattr(langfuse.settings, "TELEMETRY_ENABLED", False)
    monkeypatch.setattr(langfuse.settings, "TELEMETRY_PROVIDER", "noop")
    monkeypatch.setattr(langfuse.settings, "LANGFUSE_PUBLIC_KEY", "")

    assert langfuse.emit_refund_trace(trace_id="x", ticket_id=1, spans=[]) is False


def test_langfuse_post_failure_is_isolated(monkeypatch):
    from app.observability import langfuse

    def boom(payload):
        raise RuntimeError("network down")

    monkeypatch.setattr(langfuse.settings, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(langfuse.settings, "TELEMETRY_PROVIDER", "langfuse")
    monkeypatch.setattr(langfuse.settings, "LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setattr(langfuse.settings, "LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setattr(langfuse, "_post", boom)
    monkeypatch.setattr(langfuse, "_queue", None)

    # 入队本身不抛错；发送线程失败只记录日志
    assert langfuse.emit_refund_trace(trace_id="x", ticket_id=1, spans=[{"name": "s"}]) is True
    langfuse.shutdown(timeout=1)
