"""检查 CubeSandbox 连接并列出模板，不会自动写入密钥或猜测代理节点。"""
from __future__ import annotations

import argparse
import os
import sys

from cubesandbox import Config, Sandbox, Template


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="检查 CubeSandbox 并列出可用模板")
    parser.add_argument("--api-url", default=os.getenv("CUBESANDBOX_API_URL", "http://127.0.0.1:3000"))
    parser.add_argument("--api-key", default=os.getenv("CUBESANDBOX_API_KEY", ""))
    parser.add_argument("--template-id", default=os.getenv("CUBESANDBOX_TEMPLATE_ID", ""))
    args = parser.parse_args()
    config = Config(api_url=args.api_url, api_key=args.api_key or None, template_id=args.template_id or None)
    try:
        health = Sandbox.health(config=config)
        print(f"CubeAPI 健康检查：{health}")
        templates = Template.list(config=config)
    except Exception as exc:
        print(f"连接失败：{exc}")
        print("请确认 CubeSandbox 服务已启动、API URL 可访问，并检查 CUBESANDBOX_API_KEY。")
        return 1
    if not templates:
        print("连接成功，但没有可用模板；请先创建 Python 模板。")
        return 1
    print("可用模板：")
    for template in templates:
        print(f"- {template.template_id}: {template.name}")
    if args.template_id and not any(t.template_id == args.template_id for t in templates):
        print(f"模板不存在：{args.template_id}")
        return 1
    print("模板检查通过。proxy_node_ip 仍需填写 CubeProxy 实际节点 IP。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
