"""评测样本集的结构校验和加载（Golden + 意图样本）。"""
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class GoldenCase(BaseModel):
    case_id: str = Field(pattern=r"^G\d{2}$")
    amount: float = Field(gt=0)
    ocr_confidence: float = Field(ge=0, le=1)
    fraud_score: int = Field(ge=0, le=100)
    sentiment: Literal["LOW", "MEDIUM", "HIGH"]
    expected_route: Literal["AUTO_REFUND", "HUMAN_REVIEW"]
    expected_reasons: list[str] = Field(min_length=1)
    security_expectation: Literal["ALLOW_AUTO", "FORCE_HUMAN"]


def load_golden_cases(path: Path) -> list[GoldenCase]:
    """按行读取 JSONL，并在加载阶段拒绝无效评测数据。"""
    cases: list[GoldenCase] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(GoldenCase.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Golden Dataset 第 {line_no} 行无效: {exc}") from exc
    return cases


class IntentSample(BaseModel):
    """工单 8 意图样本：口语化客诉/退款输入 + 期望意图与期望分流。"""

    case_id: str = Field(pattern=r"^I\d{3}$")
    text: str = Field(min_length=1)
    expected_label: Literal["refund_request", "complaint", "malicious", "general"]
    expected_route: Literal["strong_signal", "llm_judge"]
    supporting_text: str = ""


def load_intent_samples(path: Path) -> list[IntentSample]:
    """按行读取 JSONL，并在加载阶段拒绝无效评测数据。"""
    samples: list[IntentSample] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            samples.append(IntentSample.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"意图样本第 {line_no} 行无效: {exc}") from exc
    return samples
