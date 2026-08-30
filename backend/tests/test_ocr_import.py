import builtins
from pathlib import Path
import sys
from types import ModuleType


def _create_model_dirs(root: Path) -> None:
    for name in ("det", "rec", "cls"):
        model_dir = root / name
        model_dir.mkdir(parents=True)
        (model_dir / "inference.pdmodel").write_bytes(b"model")
        (model_dir / "inference.pdiparams").write_bytes(b"params")


def test_get_ocr_uses_explicit_models_and_disables_unsafe_optimizations(monkeypatch, tmp_path):
    from app.agents import ocr

    calls = []
    kwargs = {}
    _create_model_dirs(tmp_path)
    fake_paddleocr = ModuleType("paddleocr")
    fake_paddleocr.PaddleOCR = lambda **values: kwargs.update(values) or object()
    monkeypatch.setitem(sys.modules, "paddleocr", fake_paddleocr)
    real_import = builtins.__import__

    def track_import(name, *args, **kwargs):
        if name in {"scipy", "paddleocr"}:
            calls.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", track_import)
    monkeypatch.setattr(ocr, "_ocr", None)
    monkeypatch.setattr(ocr.settings, "OCR_MODEL_DIR", str(tmp_path))

    ocr._get_ocr()

    assert calls.index("scipy") < calls.index("paddleocr")
    assert kwargs["det_model_dir"] == str(tmp_path / "det")
    assert kwargs["rec_model_dir"] == str(tmp_path / "rec")
    assert kwargs["cls_model_dir"] == str(tmp_path / "cls")
    assert kwargs["use_gpu"] is False
    assert kwargs["enable_mkldnn"] is False


def test_get_ocr_refuses_implicit_model_download(monkeypatch, tmp_path):
    from app.agents import ocr

    monkeypatch.setattr(ocr, "_ocr", None)
    monkeypatch.setattr(ocr.settings, "OCR_MODEL_DIR", str(tmp_path / "missing"))

    try:
        ocr._get_ocr()
    except RuntimeError as exc:
        assert "OCR 模型文件不完整" in str(exc)
    else:
        raise AssertionError("模型缺失时不得触发 PaddleOCR 隐式下载")
