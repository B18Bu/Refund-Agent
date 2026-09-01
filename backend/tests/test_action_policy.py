from app.agents import nodes
from app.security.action_policy import ActionPolicy, ActionRequest, ActionVerdict


def low_risk_state() -> dict:
    return {
        "amount": 128.0,
        "ocr_confidence": 0.95,
        "fraud_score": 20,
        "sentiment": "LOW",
        "ocr_text": "金额128元",
        "critic_risk": 0.0,
        "security_flags": [],
    }


class RejectingPolicy:
    def evaluate(self, request: ActionRequest) -> ActionVerdict:
        return ActionVerdict(False, "unregistered_action")


def test_policy_denies_unregistered_tool_and_payment_execution():
    policy = ActionPolicy()

    for action, expected_reason in (
        ("invoke_tool", "tool_invocation_not_supported"),
        ("payment_execution", "payment_execution_not_supported"),
    ):
        verdict = policy.evaluate(
            ActionRequest(
                action=action,
                decision="AUTO_REFUND",
                tool_name="Direct_Refund_API",
            )
        )

        assert verdict.allowed is False
        assert verdict.reason == expected_reason


def test_policy_rejects_auto_refund_record_when_a_tool_name_is_present():
    verdict = ActionPolicy().evaluate(
        ActionRequest(
            action="record_auto_refund",
            decision="AUTO_REFUND",
            tool_name="Direct_Refund_API",
        )
    )

    assert verdict == ActionVerdict(False, "tool_invocation_not_supported")


def test_policy_denies_non_finite_security_risk():
    policy = ActionPolicy()

    for risk in (float("nan"), float("inf"), float("-inf")):
        verdict = policy.evaluate(
            ActionRequest(
                action="record_auto_refund",
                decision="AUTO_REFUND",
                security_risk=risk,
            )
        )

        assert verdict == ActionVerdict(False, "security_risk_invalid")


def test_policy_allows_only_safe_decision_records():
    policy = ActionPolicy()

    auto_refund = policy.evaluate(
        ActionRequest(action="record_auto_refund", decision="AUTO_REFUND")
    )
    human_review = policy.evaluate(
        ActionRequest(action="request_human_review", decision="HUMAN_REVIEW")
    )
    invalid_human_review = policy.evaluate(
        ActionRequest(action="request_human_review", decision="AUTO_REFUND")
    )
    flagged_refund = policy.evaluate(
        ActionRequest(
            action="record_auto_refund",
            decision="AUTO_REFUND",
            security_flags=("dangerous_tool",),
        )
    )
    risky_refund = policy.evaluate(
        ActionRequest(
            action="record_auto_refund",
            decision="AUTO_REFUND",
            security_risk=0.85,
        )
    )

    assert auto_refund == ActionVerdict(True, "record_auto_refund_allowed")
    assert human_review == ActionVerdict(True, "human_review_allowed")
    assert invalid_human_review == ActionVerdict(False, "unregistered_action")
    assert flagged_refund == ActionVerdict(False, "security_flags_present")
    assert risky_refund == ActionVerdict(False, "security_risk_at_threshold")


def test_graph_policy_denial_converts_auto_refund_to_human_review(monkeypatch):
    monkeypatch.setattr(nodes, "_action_policy", RejectingPolicy())

    state = nodes.decision_node(low_risk_state())

    assert state["decision"] == "HUMAN_REVIEW"
    assert state["final_decision"] == "PENDING"
    assert state["decision_reasons"][-1] == "action_policy_denied"
    assert state["evidence_audit"]["action_policy"] == {
        "allowed": False,
        "reason": "unregistered_action",
    }
