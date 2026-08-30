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
