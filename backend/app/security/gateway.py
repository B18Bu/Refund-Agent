"""企业级 Agent 零信任安全网关：DLP 脱敏 + Critic 注入检测。

对应 docs/sec_spec.md：
- DLP：对手机号/身份证/银行卡/API Key/邮箱做掩码，掩码文本供 LLM/日志/观测使用。
- Critic：规则引擎对输入评分（0~1），阈值（默认 0.85）以上拦截并抛 SecurityException；
  可选 LLM 增强，失败不影响规则结论（AGENTS.md 规则 5：路由/拦截保持确定性）。
"""
from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass

from app.config import settings
from app.security.ner import NerDetector, get_ner_detector


class SecurityException(Exception):
    """命中注入/越狱拦截信号。"""

    def __init__(self, risk: float, rules: list[str]):
        super().__init__(f"security_injection_detected risk={risk:.2f} rules={rules}")
        self.risk = risk
        self.rules = rules


@dataclass(frozen=True)
class CriticResult:
    risk: float
    rules: list[str]
    annotation: str


class _CriticAnnotator:
    """可选 LLM 注释器：只返回是否可用，模型内容不离开本地调用栈。"""

    def annotate(self, summary: str) -> None:
        from app.agents.llm import get_client

        client = get_client()
        if client is None:
            raise RuntimeError("annotation client unavailable")
        client.chat.completions.create(
            model=settings.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "仅确认已收到脱敏安全摘要；不得提出操作或改变安全结论。"},
                {"role": "user", "content": summary},
            ],
            temperature=0,
            timeout=5,
        )


_critic_annotator = _CriticAnnotator()


# ============ DLP：PII 脱敏 ============

_MOBILE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_ID_CARD_RE = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")
_BANK_CARD_RE = re.compile(r"(?<!\d)(62\d{14,17})(?!\d)")
_API_KEY_RE = re.compile(r"(?i)(?:sk-[A-Za-z0-9_-]{8,}|pk-lf-[A-Za-z0-9_-]{8,})")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class DLP:
    """敏感数据脱敏。mask 返回 (掩码文本, 实体清单)。"""

    @staticmethod
    def mask(text: str, detector: NerDetector | None = None) -> tuple[str, list[str]]:
        raw = text or ""
        replacements: list[tuple[int, int, str, str]] = []

        def add_regex(pattern: re.Pattern, entity: str, render) -> None:
            for match in pattern.finditer(raw):
                start, end = match.span()
                if any(start < current_end and current_start < end for current_start, current_end, _, _ in replacements):
                    continue
                replacements.append((start, end, render(match.group(0)), entity))

        add_regex(_MOBILE_RE, "mobile_phone", lambda value: f"{value[:3]}****{value[-4:]}")
        add_regex(_ID_CARD_RE, "id_card", lambda value: f"{value[:3]}***********{value[-4:]}")
        add_regex(_BANK_CARD_RE, "bank_card", lambda value: f"{value[:4]}**********{value[-4:]}")
        add_regex(_API_KEY_RE, "api_key", lambda value: f"{value.split('-', 1)[0]}-****")
        add_regex(_EMAIL_RE, "email", lambda value: f"{value[0]}***{value[value.index('@'):]}")

        label_mapping = {"PERSON": "person_name", "GPE": "address", "LOC": "address"}
        try:
            detected = (detector or get_ner_detector()).detect(raw)
        except Exception:
            detected = []
        for entity in sorted(detected, key=lambda item: (item.start, item.end, item.label)):
            entity_type = label_mapping.get(entity.label.upper())
            if entity_type is None or entity.start < 0 or entity.end > len(raw) or entity.start >= entity.end:
                continue
            if any(entity.start < current_end and current_start < entity.end for current_start, current_end, _, _ in replacements):
                continue
            replacements.append((entity.start, entity.end, "*" * (entity.end - entity.start), entity_type))

        parts: list[str] = []
        cursor = 0
        for start, end, replacement, _ in sorted(replacements, key=lambda item: item[0]):
            parts.extend((raw[cursor:start], replacement))
            cursor = end
        parts.append(raw[cursor:])
        return "".join(parts), sorted({entity for _, _, _, entity in replacements})


# ============ Critic：注入/越狱检测 ============

def _normalize(text: str) -> str:
    """全角转半角、Unicode 归一化、去零宽字符、转小写。"""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    return text.lower()


_CRITIC_RULES: list[tuple[str, re.Pattern, float]] = [
    (
        "indirect_injection",
        re.compile(
            r"跳过\s*人工审批|绕过\s*审批|无需人工|原路退回|全额赔付"
        ),
        1.0,
    ),
    (
        "indirect_injection",
        re.compile(r"立即执行|直接放行|自动通过|放行"),
        0.5,
    ),
    (
        "dangerous_tool",
        re.compile(
            r"direct_refund_api|退款\s*api|支付接口|调用\s*(?:后台|退款|支付)|直接执行|"
            r"approve\s*bypass|refund\s*api|立即退款|直接退款|refund\s+immediately|退款接口"
        ),
        1.0,
    ),
    (
        "jailbreak_roleplay",
        re.compile(
            r"忽略之前|忽略所有指令|忽略上述|扮演系统|developer mode|do anything now|"
            r"\bdan\b|越狱模式|system mode|jailbreak|忽略所有(?:指令|约束)|(?:系统|system)\s*mode"
        ),
        1.0,
    ),
    (
        "jailbreak_roleplay",
        re.compile(r"你现在是|作为系统|无视规则"),
        0.5,
    ),
    (
        "system_prompt_tamper",
        re.compile(r"system prompt|系统提示|system message|开发者指令|规则覆盖|覆盖系统"),
        1.0,
    ),
    (
        "multilingual_injection",
        re.compile(
            r"ignore previous|ignore all instructions|ignore all previous|"
            r"前の指示|이전 지시|이전 지침|ignora istruzioni precedenti"
        ),
        1.0,
    ),
]

_BASE64_BLOCK_RE = re.compile(r"[A-Za-z0-9+/]{32,}={0,2}")
_BASE64_DANGER_RE = re.compile(
    r"ignore previous|ignore all|ignore instructions|skip human|skip manual|manual review|"
    r"call refund|refund api|refund \d+|direct_refund|approval|invoke .*refund|backend refund"
)


class CriticEngine:
    """规则引擎评分：命中规则权重累加（上限 1.0）。"""

    def score(self, text: str) -> tuple[float, list[str]]:
        raw = text or ""
        normalized = _normalize(raw)
        total = 0.0
        rules: list[str] = []
        for name, pattern, weight in _CRITIC_RULES:
            if pattern.search(normalized):
                total += weight
                rules.append(name)
        # base64 必须从原文提取（归一化会破坏编码），解码后再归一化判词
        for block in _BASE64_BLOCK_RE.findall(raw):
            try:
                decoded = base64.b64decode(block).decode("utf-8", errors="ignore").lower()
            except Exception:
                continue
            if _BASE64_DANGER_RE.search(decoded):
                total += 1.0
                rules.append("base64_obfuscation")
                break
        return min(1.0, total), rules

    def is_blocked(self, text: str, threshold: float = 0.85) -> bool:
        risk, _ = self.score(text)
        return risk >= threshold

    def inspect(self, text: str) -> CriticResult:
        """确定性规则先完成评分；LLM 仅对脱敏摘要做可用性注释。"""
        risk, rules = self.score(text)
        if not settings.SECURITY_LLM_ENHANCE:
            return CriticResult(risk, rules, "llm_annotation_disabled")
        try:
            summary, _ = DLP.mask(text or "")
            _critic_annotator.annotate(summary[:512])
        except Exception:
            return CriticResult(risk, rules, "llm_annotation_unavailable")
        return CriticResult(risk, rules, "llm_annotation_available")

    def block_or_raise(self, text: str, threshold: float = 0.85) -> None:
        risk, rules = self.score(text)
        if risk >= threshold:
            raise SecurityException(risk, rules)


def prepare_llm_material(amount: float, ocr_text: str) -> str:
    """构造喂给 LLM 的材料：OCR 文本先脱敏，PII 不以明文进入模型。"""
    masked, _ = DLP.mask(ocr_text or "")
    return f"退款金额：{amount}\n凭证 OCR：{masked}"
