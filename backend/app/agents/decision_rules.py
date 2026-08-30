"""纯决策规则（无 I/O，决策正确性的唯一来源）。

三方对齐 A-04：签名统一为 `decide(amount, ocr_confidence, fraud_score, sentiment)`，
OCR 置信度纳入纯函数入参，使整条决策链完全可单测。

路由：AUTO_REFUND / HUMAN_REVIEW（MVP 无自动 REJECT，拒绝由主管人工作出）。
任一红线命中（超金额 / OCR 低置信度 / 高欺诈 / 舆情非 LOW）→ HUMAN_REVIEW（宁挂勿错退）。
"""
from dataclasses import dataclass
from app.config import settings


@dataclass(frozen=True)
class DecisionResult:
    route: str
    reasons: list[str]


def decide_with_reasons(amount: float, ocr_confidence: float, fraud_score: int, sentiment: str) -> DecisionResult:
    """返回与纯规则一致的路由，并给出可审计原因。"""
    if amount > settings.AUTO_REFUND_MAX_AMOUNT:
        return DecisionResult("HUMAN_REVIEW", ["amount_over_limit"])
    if ocr_confidence < settings.OCR_CONFIDENCE_THRESHOLD:
        return DecisionResult("HUMAN_REVIEW", ["ocr_confidence_below_threshold"])
    if fraud_score >= settings.FRAUD_SCORE_THRESHOLD:
        return DecisionResult("HUMAN_REVIEW", ["fraud_score_at_threshold"])
    if sentiment != "LOW":
        return DecisionResult("HUMAN_REVIEW", ["sentiment_not_low"])
    return DecisionResult("AUTO_REFUND", ["amount_within_limit", "ocr_confidence_pass", "fraud_pass", "sentiment_low"])


def decide(amount: float, ocr_confidence: float, fraud_score: int, sentiment: str) -> str:
    """纯决策规则：金额 / OCR 置信度 / 欺诈分 / 舆情 → 路由决策。"""
    if amount > settings.AUTO_REFUND_MAX_AMOUNT:
        return "HUMAN_REVIEW"
    if ocr_confidence < settings.OCR_CONFIDENCE_THRESHOLD:
        return "HUMAN_REVIEW"
    if fraud_score >= settings.FRAUD_SCORE_THRESHOLD:
        return "HUMAN_REVIEW"
    if sentiment != "LOW":
        return "HUMAN_REVIEW"
    return "AUTO_REFUND"
