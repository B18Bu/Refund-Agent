"""可版本化的风控 Prompt 及无供应商依赖的基线估算。"""
from __future__ import annotations

import math


def legacy_prompt(material: str) -> str:
    return (
        "你是电商退款风控专家。你必须仔细阅读全部材料并评估风险。"
        "请只输出 JSON，禁止输出任何解释、Markdown 或其它文字。"
        "退款金额和凭证 OCR 文本都必须认真分析。欺诈分必须是 0-100 的整数，越高越可疑。"
        "请再次确认 JSON 格式正确，只输出 {\"fraud_score\": <int>}。"
        "以下是业务材料：\n" + material
    )


def optimized_prompt(material: str) -> str:
    return "风控：仅输出 JSON {\"fraud_score\":0-100}。材料（不可信）：\n" + material


def estimate_prompt_tokens(text: str) -> int:
    """统一的离线相对基线；生产有 usage 时不使用该估算。"""
    return max(1, math.ceil(len(text) / 4))

