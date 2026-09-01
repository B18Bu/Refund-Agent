"""本地 NER 适配器：只接受显式配置的本地 spaCy 模型目录。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.config import settings


@dataclass(frozen=True)
class NerEntity:
    label: str
    start: int
    end: int


class NerDetector(Protocol):
    status: str

    def detect(self, text: str) -> list[NerEntity]: ...


class _UnavailableNerDetector:
    def __init__(self, status: str):
        self.status = status

    def detect(self, text: str) -> list[NerEntity]:
        return []


class _SpacyNerDetector:
    status = "available"

    def __init__(self, model: object):
        self._model = model

    def detect(self, text: str) -> list[NerEntity]:
        try:
            doc = self._model(text)
        except Exception:
            self.status = "degraded"
            return []
        return [NerEntity(entity.label_, entity.start_char, entity.end_char) for entity in doc.ents]


_cached_key: tuple[bool, str] | None = None
_cached_detector: NerDetector | None = None


def get_ner_detector() -> NerDetector:
    """返回本地模型适配器；任何配置或加载失败都显式降级且不访问网络。"""
    global _cached_key, _cached_detector
    key = (settings.DLP_NER_ENABLED, settings.DLP_NER_MODEL_PATH)
    if key == _cached_key and _cached_detector is not None:
        return _cached_detector

    enabled, model_path = key
    if not enabled:
        detector: NerDetector = _UnavailableNerDetector("disabled")
    elif not model_path or not Path(model_path).is_dir():
        detector = _UnavailableNerDetector("degraded")
    else:
        try:
            import spacy

            detector = _SpacyNerDetector(spacy.load(model_path))
        except Exception:
            detector = _UnavailableNerDetector("degraded")

    _cached_key = key
    _cached_detector = detector
    return detector


def get_ner_status() -> str:
    return get_ner_detector().status
