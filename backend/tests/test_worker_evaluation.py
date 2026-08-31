from contextlib import nullcontext
from types import SimpleNamespace

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models as _models  # noqa: F401  # 在独立运行本模块时先注册全部表


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

    orig = RuntimeError("duplicate key")
    orig.diag = SimpleNamespace(constraint_name="ux_agent_evaluation_runs_run_id")

    def duplicate():
        raise IntegrityError("insert", {}, orig)

    assert try_persist_evaluation(duplicate) is True


def test_other_integrity_errors_are_not_idempotent_successes():
    from app.evaluation.repository import try_persist_evaluation

    def invalid_foreign_key():
        raise IntegrityError("insert", {}, RuntimeError("foreign key"))

    assert try_persist_evaluation(invalid_foreign_key) is False


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


def test_baseline_covers_same_fraud_and_sentiment_call_scope():
    from app.agents.prompts import estimate_prompt_tokens, legacy_prompt
    from app.evaluation.repository import build_evaluation

    state = {
        "amount": 128.0,
        "ocr_text": "清晰商品图",
        "ocr_confidence": 0.95,
        "fraud_score": 20,
        "sentiment": "LOW",
        "decision": "AUTO_REFUND",
        "decision_reasons": [
            "amount_within_limit", "ocr_confidence_pass", "fraud_pass", "sentiment_low",
        ],
        "token_usage": {
            "fraud": {"input_tokens": 20, "output_tokens": 2, "total_tokens": 22, "measurement_type": "estimated"},
            "sentiment": {"input_tokens": 10, "output_tokens": 1, "total_tokens": 11, "measurement_type": "estimated"},
        },
    }
    material = "退款金额：128.0\n凭证 OCR：清晰商品图"

    record = build_evaluation(ticket_id=1, run_id="scope:start", state=state)

    assert record.baseline_input_tokens > estimate_prompt_tokens(legacy_prompt(material))


def test_duplicate_start_run_persists_only_one_record(db_engine, db_session, monkeypatch):
    from app.evaluation import repository
    from app.evaluation.models import AgentEvaluationRun
    from app.models import Decision, Role, Ticket, TicketStatus, User

    user = User(username="evaluation-idempotent", password_hash="not-used", role=Role.CS)
    db_session.add(user)
    db_session.flush()
    ticket = Ticket(
        ticket_no="evaluation-idempotent-ticket",
        user_id=user.id,
        amount=128,
        image_paths=[],
        status=TicketStatus.COMPLETED,
        decision=Decision.AUTO_REFUNDED,
    )
    db_session.add(ticket)
    db_session.commit()
    Session = sessionmaker(bind=db_engine)
    monkeypatch.setattr(repository, "SessionLocal", Session)
    state = {
        "amount": 128.0,
        "ocr_text": "清晰商品图",
        "ocr_confidence": 0.95,
        "fraud_score": 20,
        "sentiment": "LOW",
        "decision": "AUTO_REFUND",
        "decision_reasons": [
            "amount_within_limit", "ocr_confidence_pass", "fraud_pass", "sentiment_low",
        ],
    }

    assert repository.record_evaluation(ticket_id=ticket.id, run_id="same:start", state=state)
    assert repository.record_evaluation(ticket_id=ticket.id, run_id="same:start", state=state)

    with Session() as verification:
        assert verification.query(AgentEvaluationRun).filter_by(run_id="same:start").count() == 1


class _FakeGraph:
    def __init__(self, state, next_nodes=()):
        self.state = state
        self.next_nodes = next_nodes
        self.stream_inputs = []

    def compile(self, checkpointer):
        return self

    def get_state(self, _cfg):
        return SimpleNamespace(values=self.state, next=self.next_nodes)

    def stream(self, graph_input, **_kwargs):
        self.stream_inputs.append(graph_input)
        return iter(())


def _patch_process_dependencies(monkeypatch, graph):
    from app.worker import consumer

    updates = []
    monkeypatch.setattr(consumer, "build_graph", lambda: graph)
    monkeypatch.setattr(consumer, "get_checkpointer", lambda: nullcontext(object()))
    monkeypatch.setattr(consumer, "update_ticket", lambda thread_id, **fields: updates.append((thread_id, fields)))
    monkeypatch.setattr(consumer, "publish_event", lambda *_args, **_kwargs: None)
    return consumer, updates


def test_resume_action_without_type_does_not_record_evaluation(monkeypatch):
    graph = _FakeGraph({"final_decision": "APPROVED"})
    consumer, _ = _patch_process_dependencies(monkeypatch, graph)
    recorded = []
    monkeypatch.setattr(consumer, "record_evaluation", lambda **kwargs: recorded.append(kwargs))

    consumer.process({"ticket_id": "1", "thread_id": "thread-resume", "resume_action": "APPROVE"})

    assert recorded == []


def test_failed_evaluation_observation_does_not_change_completed_decision(monkeypatch):
    from app.models import TicketStatus

    graph = _FakeGraph({"final_decision": "AUTO_REFUNDED"})
    consumer, updates = _patch_process_dependencies(monkeypatch, graph)
    ticket = SimpleNamespace(amount=128.0, image_paths=[])
    fake_db = SimpleNamespace(get=lambda *_args: ticket)

    class FakeSession:
        def __enter__(self):
            return fake_db

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(consumer, "SessionLocal", FakeSession)
    monkeypatch.setattr(consumer, "record_evaluation", lambda **_kwargs: False)

    consumer.process({"ticket_id": "1", "thread_id": "thread-start", "type": "START"})

    assert any(
        fields.get("status") == TicketStatus.COMPLETED
        and str(fields.get("decision")) == "Decision.AUTO_REFUNDED"
        for _, fields in updates
    )


def test_failed_evaluation_observation_keeps_human_review_suspended(monkeypatch):
    from app.models import TicketStatus

    graph = _FakeGraph(
        {
            "ocr_text": "清晰商品图",
            "ocr_confidence": 0.95,
            "fraud_score": 60,
            "sentiment": "LOW",
        },
        next_nodes=("human_review",),
    )
    consumer, updates = _patch_process_dependencies(monkeypatch, graph)
    ticket = SimpleNamespace(amount=350.0, image_paths=[])
    fake_db = SimpleNamespace(get=lambda *_args: ticket)

    class FakeSession:
        def __enter__(self):
            return fake_db

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(consumer, "SessionLocal", FakeSession)
    monkeypatch.setattr(consumer, "record_evaluation", lambda **_kwargs: False)
    failed = []
    monkeypatch.setattr(consumer, "mark_failed", lambda *_args: failed.append(True))

    consumer.process({"ticket_id": "1", "thread_id": "thread-suspended", "type": "START"})

    assert any(fields.get("status") == TicketStatus.SUSPENDED for _, fields in updates)
    assert failed == []
