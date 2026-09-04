import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))


def test_build_multipart_body_contains_amount_and_file(tmp_path):
    from scripts.scenario_e2e import build_multipart_body

    image = tmp_path / "goods128.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    body = build_multipart_body("----test-boundary", 128.0, image)

    assert b'name="amount"' in body
    assert b'128.0' in body
    assert b'name="files"; filename="goods128.png"' in body
    assert b"D:/Claude Code" not in body


def test_scenario_uses_current_approval_endpoint():
    from scripts.scenario_e2e import APPROVAL_ENDPOINT

    assert APPROVAL_ENDPOINT == "/approval"


def test_ocr_client_reports_missing_image(monkeypatch):
    from app.agents import ocr

    monkeypatch.setattr(ocr, "_get_ocr", lambda: (_ for _ in ()).throw(AssertionError("should not initialize")))
    result = ocr.OcrClient().extract("missing-image.png")

    assert result.text == ""
    assert result.confidence == 0.0
    assert result.error_code == "OCR_INPUT_NOT_FOUND"
