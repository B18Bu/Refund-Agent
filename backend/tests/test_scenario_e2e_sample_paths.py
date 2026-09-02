"""端到端脚本必须把生成的样例置于受管理的样例目录。"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def test_scenario_e2e_uses_managed_sample_directory():
    root = Path(__file__).resolve().parents[2]
    spec = spec_from_file_location("scenario_e2e", root / "scripts" / "scenario_e2e.py")
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.SAMPLE_DIR == root / "docs" / "assets" / "samples"
