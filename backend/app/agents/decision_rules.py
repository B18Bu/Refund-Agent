"""纯决策规则（无 I/O，决策正确性的唯一来源）。

三方对齐 A-04：签名统一为 `decide(amount, ocr_confidence, fraud_score, sentiment)`，
OCR 置信度纳入纯函数入参，使整条决策链完全可单测。
金额一致性校验：可选入参 `ocr_text`（凭证 OCR 全文），从其中确定性提取识别金额，
与申请金额做字符串级比较；识别不到金额或金额不一致 → 强制人工（宁挂勿错退）。
三维可审计判断：价格一致性（识别金额 vs 申请金额）、订单真实性（OCR 是否含订单号）、
商品一致性（OCR 是否含商品/凭证描述）；后两维为审计维度，不阻断路由，供人工与观测展示。

路由：AUTO_REFUND / HUMAN_REVIEW（MVP 无自动 REJECT，拒绝由主管人工作出）。
任一红线命中（超金额 / OCR 低置信度 / 高欺诈 / 舆情非 LOW）→ HUMAN_REVIEW（宁挂勿错退）。
"""
import re
from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class DecisionResult:
    route: str
    reasons: list[str]


# 金额关键词：优先锚定「金额/合计/总计」等上下文，避免把订单号、日期误判为金额。
_AMOUNT_KEYWORDS = (
    "金额|订单金额|合计|总计|小计|实付|实收|付款|退款|应付|应收|总价|价格|货款|总额|"
    "total|amount|price|pay|sum|subtotal"
)
# 三类金额模式（按优先级）：
# 1) 金额关键词附近的数字；2) 货币符号前缀（¥/￥/$）；3) 数字后跟货币单位（元/圆/块/人民币）。
# 第三类用于覆盖「订单号128元」这类语义明确是金额、但关键词不在列表中的表述；
# 纯订单号（如「订单号 800123」无货币单位）不会被误判。
_AMOUNT_RE = re.compile(
    rf"(?:{_AMOUNT_KEYWORDS})\s*[:：]?\s*[¥￥$]?\s*(\d+(?:,\d{{3}})*)(?:\.(\d{{1,2}}))?"
    rf"|[¥￥$]\s*(\d+(?:,\d{{3}})*)(?:\.(\d{{1,2}}))?"
    rf"|(\d+(?:,\d{{3}})*)(?:\.(\d{{1,2}}))?\s*(?:元|圆|块|人民币|RMB)",
    re.IGNORECASE,
)

_ORDER_NO_RE = re.compile(
    r"(?:订单号|订单编号|单号|order\s*no\.?|order#)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9_-]{0,31})",
    re.IGNORECASE,
)

_GOODS_KEYWORDS = ("商品", "货物", "正品", "全新", "破损", "发票", "凭证", "订单", "缺货", "质量问题")


def extract_refund_amounts(ocr_text: str) -> list[str]:
    """从 OCR 文本中确定性提取识别金额（单位：元），统一格式化为两位小数。

    - 识别金额关键词附近、货币符号前缀、或数字后跟货币单位的数值，避免把纯订单号、日期误判为金额。
    - 千分位分隔符（如 1,280.50）会被规范化。
    - 返回形如 ["350.00"] 的列表，供与申请金额做字符串级比较。
    """
    amounts: list[str] = []
    for match in _AMOUNT_RE.finditer(ocr_text or ""):
        int_part = None
        frac_part = "0"
        for idx in (1, 3, 5):  # 三个备选分支的整数部分组号
            if match.group(idx) is not None:
                int_part = match.group(idx).replace(",", "")
                frac_part = match.group(idx + 1) or "0"
                break
        if int_part is None:
            continue
        value = float(f"{int_part}.{frac_part}")
        amounts.append(f"{value:.2f}")
    return amounts


def extract_order_number(ocr_text: str) -> str | None:
    """从 OCR 文本提取订单号（订单号/订单编号/单号 + 4-32 位字母数字）。"""
    match = _ORDER_NO_RE.search(ocr_text or "")
    return match.group(1) if match else None


def _has_goods_evidence(ocr_text: str) -> bool:
    return any(keyword in (ocr_text or "") for keyword in _GOODS_KEYWORDS)


def audit_evidence(amount: float, ocr_text: str | None) -> dict[str, str]:
    """输出三维可审计判断：价格一致性 / 订单真实性 / 商品一致性。

    - price_consistency：match / mismatch / missing / unverified（阻断路由，见 decide）
    - order_authenticity：pass（OCR 含订单号）/ unverified（无订单号，审计维度，不阻断）
    - goods_consistency：pass（OCR 含商品/凭证描述）/ unverified（审计维度，不阻断）
    """
    expected = f"{amount:.2f}"
    if ocr_text is None:
        price = "unverified"
    else:
        recognized = extract_refund_amounts(ocr_text)
        if not recognized:
            price = "missing"
        elif expected in recognized:
            price = "match"
        else:
            price = "mismatch"
    order = "pass" if extract_order_number(ocr_text or "") else "unverified"
    goods = "pass" if _has_goods_evidence(ocr_text or "") else "unverified"
    return {
        "price_consistency": price,
        "order_authenticity": order,
        "goods_consistency": goods,
    }


def management_suggestion(route: str, reasons: list[str]) -> str:
    """根据路由与首因给出退款状态管理建议（面向主管展示）。"""
    if route == "AUTO_REFUND":
        return "建议自动退赔：金额/订单/商品校验一致且风险为低"
    if "security_injection_detected" in reasons:
        return "建议人工复核：凭证中检测到注入/越狱风险，禁止自动退赔"
    if "ocr_amount_mismatch" in reasons:
        return "建议人工复核价格：识别金额与申请金额不一致"
    if "ocr_amount_missing" in reasons:
        return "建议人工核对凭证金额：OCR 未识别到可核对金额"
    if "amount_over_limit" in reasons:
        return "建议人工审批：申请金额超过自动退赔上限"
    if "ocr_confidence_below_threshold" in reasons:
        return "建议人工复核凭证清晰度：OCR 置信度不足"
    if "fraud_score_at_threshold" in reasons:
        return "建议加强风险核查后人工审批"
    if "sentiment_not_low" in reasons:
        return "建议优先安抚客户并人工审批"
    return "建议人工复核后审批"


def decide_with_reasons(
    amount: float,
    ocr_confidence: float,
    fraud_score: int,
    sentiment: str,
    ocr_text: str | None = None,
    security_risk: float = 0.0,
) -> DecisionResult:
    """返回与纯规则一致的路由，并给出可审计原因。"""
    if security_risk >= settings.SECURITY_INJECTION_THRESHOLD:
        return DecisionResult("HUMAN_REVIEW", ["security_injection_detected"])
    if amount > settings.AUTO_REFUND_MAX_AMOUNT:
        return DecisionResult("HUMAN_REVIEW", ["amount_over_limit"])
    if ocr_confidence < settings.OCR_CONFIDENCE_THRESHOLD:
        return DecisionResult("HUMAN_REVIEW", ["ocr_confidence_below_threshold"])
    if ocr_text is not None:
        recognized = extract_refund_amounts(ocr_text)
        expected = f"{amount:.2f}"
        if not recognized:
            return DecisionResult("HUMAN_REVIEW", ["ocr_amount_missing"])
        if expected not in recognized:
            return DecisionResult("HUMAN_REVIEW", ["ocr_amount_mismatch"])
    if fraud_score >= settings.FRAUD_SCORE_THRESHOLD:
        return DecisionResult("HUMAN_REVIEW", ["fraud_score_at_threshold"])
    if sentiment != "LOW":
        return DecisionResult("HUMAN_REVIEW", ["sentiment_not_low"])
    reasons = ["amount_within_limit", "ocr_confidence_pass"]
    if ocr_text is not None:
        reasons.append("ocr_amount_match")
    reasons.extend(["fraud_pass", "sentiment_low"])
    return DecisionResult("AUTO_REFUND", reasons)


def decide(
    amount: float,
    ocr_confidence: float,
    fraud_score: int,
    sentiment: str,
    ocr_text: str | None = None,
    security_risk: float = 0.0,
) -> str:
    """纯决策规则：申请金额 / OCR 置信度 / 识别金额一致性 / 欺诈分 / 舆情 → 路由决策。"""
    return decide_with_reasons(
        amount,
        ocr_confidence,
        fraud_score,
        sentiment,
        ocr_text=ocr_text,
        security_risk=security_risk,
    ).route
