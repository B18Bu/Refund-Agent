from app.config import settings
from app.security.gateway import DLP
from app.security.ner import NerEntity, get_ner_detector
from scripts.run_red_blue_test import evaluate_dlp_cases


class FakeDetector:
    def __init__(self, entities: list[NerEntity]):
        self.entities = entities

    def detect(self, text: str) -> list[NerEntity]:
        return self.entities


def test_dlp_masks_local_ner_name_and_address_without_touching_regex_entities():
    detector = FakeDetector([
        NerEntity("PERSON", 2, 4),
        NerEntity("GPE", 7, 11),
    ])

    masked, entities = DLP.mask("客户张三，地址上海浦东，电话13812340000", detector=detector)

    assert "张三" not in masked
    assert "上海浦东" not in masked
    assert "13812340000" not in masked
    assert entities == ["address", "mobile_phone", "person_name"]


def test_unconfigured_ner_preserves_regex_protection(monkeypatch):
    monkeypatch.setattr(settings, "DLP_NER_ENABLED", True)
    monkeypatch.setattr(settings, "DLP_NER_MODEL_PATH", "")

    masked, entities = DLP.mask("电话13812340000", detector=get_ner_detector())

    assert masked == "电话138****0000"
    assert entities == ["mobile_phone"]


def test_dlp_ignores_invalid_and_regex_overlapping_ner_coordinates():
    detector = FakeDetector([
        NerEntity("PERSON", -1, 2),
        NerEntity("LOC", 2, 99),
        NerEntity("PERSON", 4, 8),
        NerEntity("GPE", 2, 4),
    ])

    masked, entities = DLP.mask("地址上海，电话13812340000", detector=detector)

    assert masked == "地址**，电话138****0000"
    assert entities == ["address", "mobile_phone"]


def test_dlp_quality_gate_rejects_small_or_inaccurate_validation_set():
    report = evaluate_dlp_cases([
        {"id": "D001", "text": "联系电话13812340000", "entities": [{"type": "mobile_phone", "value": "13812340000"}]},
        {"id": "D002", "text": "客户张三申请退款", "entities": [{"type": "person_name", "value": "张三"}]},
    ])

    assert report["sample_count"] == 2
    assert report["missed_count"] == 1
    assert report["accuracy"] == 0.5
    assert report["acceptance_status"] == "not_met"
