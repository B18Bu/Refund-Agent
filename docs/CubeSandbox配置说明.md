# CubeSandbox 配置说明

项目已经接入 `cubesandbox` Python SDK，但不会伪造模板 ID 或代理节点地址。运行前需要一个可访问的 CubeAPI/CubeProxy 服务。

## 配置项

在项目根目录 `.env` 中填写：

```env
SANDBOX_PROVIDER=cube
CUBESANDBOX_API_URL=http://127.0.0.1:3000
CUBESANDBOX_API_KEY=你的 API Key
CUBESANDBOX_TEMPLATE_ID=tpl-实际模板 ID
CUBESANDBOX_PROXY_NODE_IP=实际 CubeProxy 节点 IP
CUBESANDBOX_PROXY_PORT=8080
```

`template_id` 来自 CubeSandbox 模板列表，`proxy_node_ip` 来自 CubeProxy 部署节点。两者不是 Python 包安装后自动生成的值。

## 检查

```powershell
conda activate refuse_agent
python scripts/configure_cubesandbox.py
```

脚本会检查 CubeAPI、列出模板并验证指定模板；连接失败时不会修改 `.env`。配置完整后，Worker 才会调用 `Sandbox.create(config=...)`，任务结束由适配器执行 `close()` 回收实例。

