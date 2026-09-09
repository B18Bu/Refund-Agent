# 单容器部署实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用一个受 Supervisor 管理的应用容器替换多服务 Compose 部署。

**架构：** 入口脚本初始化 PostgreSQL、Redis 和显式迁移；Supervisor 运行常驻数据库、Redis、RAG、API、两个 Worker 与 Nginx。Compose 只定义一个服务及三个持久化卷、模型和只读业务材料挂载。

**技术栈：** Debian、PostgreSQL 15、Redis Stack、Supervisor、Python 3.11、Nginx、Docker Compose。

---

### 任务 1：部署布局回归测试

**文件：**
- 创建：`backend/tests/test_single_container_deployment.py`
- 修改：`deploy/compose/docker-compose.yml`

- [ ] **步骤 1：编写失败的测试**

```python
def test_compose_defines_one_application_service():
    document = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert set(document["services"]) == {"app"}
    assert "postgres_data" in document["volumes"]
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest backend/tests/test_single_container_deployment.py -q`
预期：FAIL，当前 Compose 含多个服务。

- [ ] **步骤 3：实现最少布局**

将 Compose 改为一个 `app` 服务，保留数据卷、模型只读挂载、端口与环境变量。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest backend/tests/test_single_container_deployment.py -q`
预期：PASS。

### 任务 2：单容器入口与进程监督

**文件：**
- 创建：`deploy/single-container/entrypoint.sh`
- 创建：`deploy/single-container/supervisord.conf`
- 修改：`deploy/single-container/Dockerfile`

- [ ] **步骤 1：编写失败的入口测试**

```python
def test_entrypoint_waits_for_postgres_before_running_migrations():
    script = ENTRYPOINT.read_text(encoding="utf-8")
    assert script.index("pg_isready") < script.index("20260829_create_core_users_tickets.sql")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest backend/tests/test_single_container_deployment.py -q`
预期：FAIL，入口文件不存在。

- [ ] **步骤 3：实现入口和 Supervisor 配置**

入口以固定参数启动 PostgreSQL 与 Redis，轮询 `pg_isready` 和 `redis-cli ping`，按现有 Compose 顺序运行四个迁移 SQL，成功后 `exec supervisord`。Supervisor 管理 PostgreSQL、Redis、RAG、API、Worker、目录 Worker 和 Nginx，应用日志发送到标准输出。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest backend/tests/test_single_container_deployment.py -q`
预期：PASS。

### 任务 3：合并构建镜像与本地路由

**文件：**
- 创建：`deploy/single-container/Dockerfile`
- 修改：`frontend/nginx.conf`
- 修改：`deploy/compose/docker-compose.yml`

- [ ] **步骤 1：编写失败的路由测试**

```python
def test_nginx_proxies_api_to_container_loopback():
    assert "proxy_pass http://127.0.0.1:8000;" in NGINX_CONFIG.read_text(encoding="utf-8")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest backend/tests/test_single_container_deployment.py -q`
预期：FAIL，当前代理目标为 `api:8000`。

- [ ] **步骤 3：实现镜像和路由**

Dockerfile 使用 Node 构建前端、Python 安装后端与 RAG 依赖，并安装 PostgreSQL、Redis Stack、Nginx 与 Supervisor。Nginx API 代理改为 loopback。Compose 的 `app` 使用该 Dockerfile，仅暴露 `80:80`。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest backend/tests/test_single_container_deployment.py -q`
预期：PASS。

### 任务 4：构建与集成验证

**文件：**
- 修改：`README.md`

- [ ] **步骤 1：构建单容器镜像**

运行：`docker compose --env-file .env -f deploy/compose/docker-compose.yml build`
预期：exit 0，只有一个项目镜像。

- [ ] **步骤 2：启动并验证进程和健康检查**

运行：`docker compose --env-file .env -f deploy/compose/docker-compose.yml up -d`
预期：仅 `app` 容器运行，`http://localhost/` 与 `http://localhost/api/healthz` 可访问。

- [ ] **步骤 3：运行回归门禁**

运行：`make check`、`make frontend-build`
预期：全部通过；若网络依赖导致构建失败，保留完整日志且不得声称完成。
