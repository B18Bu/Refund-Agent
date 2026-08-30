"""CubeSandbox SDK 适配器；不在宿主机执行用户代码。"""
from __future__ import annotations

from app.sandbox.base import SandboxAdapter, SandboxResult


class CubeSandboxAdapter(SandboxAdapter):
    def __init__(self, api_url: str, template_id: str, proxy_node_ip: str, *, proxy_port: int = 8080, api_key: str = "", sandbox=None):
        from cubesandbox import Config, Sandbox

        self._sandbox = sandbox or Sandbox.create(config=Config(
            api_url=api_url,
            api_key=api_key or None,
            template_id=template_id,
            proxy_node_ip=proxy_node_ip,
            proxy_port=proxy_port,
        ))

    def run_code(self, code: str) -> str:
        result = self._sandbox.run_code(code)
        return str(getattr(result, "text", result))

    def execute(self, argv: list[str], input_dir: str, output_dir: str) -> SandboxResult:
        if argv[:2] != ["python", "-c"] or len(argv) != 3:
            raise ValueError("CubeSandbox 仅允许固定 python -c 调用")
        return SandboxResult(exit_code=0, stdout=self.run_code(argv[2]))

    def destroy(self) -> None:
        close = getattr(self._sandbox, "close", None)
        if close:
            close()
