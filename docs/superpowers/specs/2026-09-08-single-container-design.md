# 单容器部署设计

## 目标

将现有 Docker Compose 多服务部署替换为一个应用容器。该容器统一运行 PostgreSQL、Redis、显式数据库迁移、RAG 向量服务、FastAPI、两个 Worker 和前端 Nginx。对外仅暴露前端端口；各内部服务通过 loopback 通信。

## 容器边界

保留一个 Compose 服务，用于构建、环境变量、端口映射和命名卷管理。Compose 不再为每项功能创建独立服务或网络。

容器内使用 Supervisor 管理常驻进程：PostgreSQL、Redis、RAG、API、Worker、目录 Worker 和 Nginx。入口脚本负责在启动常驻进程前初始化数据目录、等待 PostgreSQL 与 Redis 可用，并按现有 SQL 文件顺序执行迁移。迁移失败时容器启动失败，应用进程不得启动。

## 数据与配置

持久化卷：PostgreSQL 数据、Redis 数据和上传目录。OCR 与 RAG 本地模型仍只读挂载，路径和现有环境变量保持兼容。数据库与 Redis 使用 `127.0.0.1` 连接；前端 Nginx 反向代理到本容器 API。

不会改变 JWT、RBAC、审批锁、Redis 幂等键、数据库条件更新、迁移 SQL 或沙箱配置。`SANDBOX_PROVIDER` 默认仍为 `disabled`。

## 失败处理

Supervisor 为常驻应用进程启用自动重启并将日志输出到容器标准输出。入口脚本是 PID 1，只负责启动前置依赖与迁移，再交由 Supervisor 管理；收到终止信号时由 Supervisor 转发给子进程。任何迁移失败、数据库或 Redis 在限定等待期内不可用均为非零退出。

## 验收

1. 一条 `docker compose ... up -d --build` 命令只创建一个项目应用容器。
2. PostgreSQL、Redis、API、两个 Worker、RAG 和 Nginx 都在该容器中运行。
3. 现有三个持久化目录在重建容器后仍保留数据。
4. `/healthz` 与前端首页可访问；迁移在应用启动前完成。
5. 现有后端测试、Golden Dataset、沙箱拒绝测试和前端构建通过。
