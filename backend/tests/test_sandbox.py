from pathlib import Path

import pytest


def test_sandbox_policy_rejects_path_escape(tmp_path):
    from app.sandbox.policy import validate_path

    root = tmp_path / "task"
    root.mkdir()
    with pytest.raises(ValueError):
        validate_path(root / ".." / "secret.txt", root)


def test_disabled_sandbox_fails_explicitly():
    from app.sandbox.base import SandboxUnavailable
    from app.sandbox.lifecycle import create_sandbox

    with pytest.raises(SandboxUnavailable):
        create_sandbox("disabled")


def test_cube_sandbox_requires_explicit_connection_settings(monkeypatch):
    from app.sandbox.base import SandboxUnavailable
    from app.sandbox.lifecycle import create_sandbox

    from app.config import settings

    monkeypatch.setattr(settings, "CUBESANDBOX_TEMPLATE_ID", "")
    monkeypatch.setattr(settings, "CUBESANDBOX_PROXY_NODE_IP", "")

    with pytest.raises(SandboxUnavailable, match="template_id"):
        create_sandbox("cube")


def test_cube_adapter_uses_sdk_config_and_destroys(monkeypatch):
    from app.sandbox.cube import CubeSandboxAdapter

    calls = []

    class FakeSandbox:
        def run_code(self, code):
            calls.append(("run", code))
            return type("Result", (), {"text": "2"})()

        def close(self):
            calls.append(("close",))

    adapter = CubeSandboxAdapter("http://127.0.0.1:3000", "tpl", "10.0.0.1", sandbox=FakeSandbox())
    assert adapter.run_code("1 + 1") == "2"
    adapter.destroy()
    assert calls == [("run", "1 + 1"), ("close",)]
