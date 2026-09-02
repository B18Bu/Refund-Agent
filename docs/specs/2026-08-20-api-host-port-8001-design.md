# API 宿主端口切换设计

**目标：** 将 Docker Compose 部署中 API 服务的宿主机访问端口从 8000 切换为 8001。

## 范围

- 修改 `docker-compose.yml` 中 `api` 服务的端口映射，从 `8000:8000` 改为 `8001:8000`。
- 重新创建 API 容器以使端口映射生效。
- 验证 `http://localhost:8001/healthz` 正常响应，并确认容器内部通信保持不变。

## 非目标

- 不改变 Uvicorn 在 API 容器内监听的 8000 端口。
- 不修改前端 Nginx 到 `api:8000` 的内部代理。
- 不修改 Vite 本地开发代理、脚本默认地址或历史文档中的 8000 示例。

## 架构与数据流

宿主机请求将通过 Docker 端口映射 `localhost:8001 -> api 容器:8000` 进入 FastAPI。前端 Nginx 位于同一 Docker 网络，继续使用服务名和容器端口 `api:8000` 访问 API；因此无需改变其代理配置。

## 验收标准

1. `docker compose ps` 显示 API 端口为 `0.0.0.0:8001->8000/tcp`。
2. `http://localhost:8001/healthz` 返回 HTTP 200 与预期健康响应。
3. API 容器保持运行，前端反向代理目标仍为 `api:8000`。
