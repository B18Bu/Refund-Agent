"""沙箱 provider 选择；未配置时安全失败。"""
from app.sandbox.base import SandboxAdapter, SandboxUnavailable
from app.config import settings


def create_sandbox(provider: str) -> SandboxAdapter:
    if provider == "disabled":
        raise SandboxUnavailable("SANDBOX_PROVIDER 未配置，拒绝执行沙箱任务")
    if provider == "cube":
        if not settings.CUBESANDBOX_TEMPLATE_ID or not settings.CUBESANDBOX_PROXY_NODE_IP:
            raise SandboxUnavailable("CubeSandbox template_id 和 proxy_node_ip 必须显式配置")
        from app.sandbox.cube import CubeSandboxAdapter
        return CubeSandboxAdapter(
            settings.CUBESANDBOX_API_URL,
            settings.CUBESANDBOX_TEMPLATE_ID,
            settings.CUBESANDBOX_PROXY_NODE_IP,
            proxy_port=settings.CUBESANDBOX_PROXY_PORT,
            api_key=settings.CUBESANDBOX_API_KEY,
        )
    if provider == "docker":
        raise SandboxUnavailable("受限 Docker 沙箱尚未配置")
    raise SandboxUnavailable(f"未知沙箱 provider: {provider}")
