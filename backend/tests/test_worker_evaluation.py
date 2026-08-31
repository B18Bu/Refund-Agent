from sqlalchemy.exc import IntegrityError


def test_resume_does_not_create_evaluation():
    from app.evaluation.repository import should_record_evaluation

    assert should_record_evaluation("RESUME") is False
    assert should_record_evaluation("START") is True


def test_evaluation_failure_is_isolated():
    from app.evaluation.repository import try_persist_evaluation

    def fail():
        raise RuntimeError("db down")

    assert try_persist_evaluation(fail) is False


def test_duplicate_run_is_an_idempotent_success():
    from app.evaluation.repository import try_persist_evaluation

    def duplicate():
        raise IntegrityError("insert", {}, RuntimeError("unique run_id"))

    assert try_persist_evaluation(duplicate) is True


def test_evaluation_record_does_not_keep_raw_ocr_text():
    from app.evaluation.repository import build_evaluation

    record = build_evaluation(
        ticket_id=1,
        run_id="thread-1:start",
        state={
            "amount": 128.0,
            "ocr_text": "身份证号和未脱敏投诉原文",
            "ocr_confidence": 0.95,
            "fraud_score": 20,
            "sentiment": "LOW",
            "decision": "AUTO_REFUND",
            "decision_reasons": [
                "amount_within_limit",
                "ocr_confidence_pass",
                "fraud_pass",
                "sentiment_low",
            ],
            "token_usage": {
                "fraud": {"input_tokens": 20, "output_tokens": 2, "total_tokens": 22, "measurement_type": "estimated"},
                "sentiment": {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11, "measurement_type": "estimated"},
            },
            "latency_breakdown": {"fraud_ms": 2.5},
        },
    )

    assert record.reason_summary == (
        "amount_within_limit,ocr_confidence_pass,fraud_pass,sentiment_low"
    )
    assert "身份证" not in record.reason_summary
    assert record.current_total_tokens == 33
    assert record.measurement_type == "estimated"
