"""动作层确定性策略：只允许记录既有退赔决策，不执行真实支付或任意工具。"""
import math
from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class ActionRequest:
    action: str
    decision: str
    security_risk: float = 0.0
    security_flags: tuple[str, ...] = ()
    tool_name: str | None = None


@dataclass(frozen=True)
class ActionVerdict:
    allowed: bool
    reason: str


class ActionPolicy:
    """自动退赔只能记录决策结果；支付和工具调用必须由未来显式能力另行接入。"""

    def evaluate(self, request: ActionRequest) -> ActionVerdict:
        if request.action == "payment_execution":
            return ActionVerdict(False, "payment_execution_not_supported")
        if request.tool_name is not None:
            return ActionVerdict(False, "tool_invocation_not_supported")
        if (
            request.action == "request_human_review"
            and request.decision == "HUMAN_REVIEW"
        ):
            return ActionVerdict(True, "human_review_allowed")
        if request.action != "record_auto_refund" or request.decision != "AUTO_REFUND":
            return ActionVerdict(False, "unregistered_action")
        if request.security_flags:
            return ActionVerdict(False, "security_flags_present")
        if not math.isfinite(request.security_risk):
            return ActionVerdict(False, "security_risk_invalid")
        if request.security_risk >= settings.SECURITY_INJECTION_THRESHOLD:
            return ActionVerdict(False, "security_risk_at_threshold")
        return ActionVerdict(True, "record_auto_refund_allowed")
