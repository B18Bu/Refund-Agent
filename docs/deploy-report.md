# 部署与压测报告（工单 5）

> 日期：2026-08-31
> 环境：Windows 11 + Docker Desktop（WSL2 后端）
> 部署方式：`docker compose`（postgres / redis / api / worker / frontend），api/worker/frontend 为最新代码镜像

## 1. 服务状态

`docker compose ps`：

| 服务 | 状态 | 端口 |
| --- | --- | --- |
| agent-postgres-1 | Up (healthy) | 5432 |
| agent-redis-1 | Up (healthy) | 6379 |
| agent-api-1 | Up | 8001→8000 |
| agent-worker-1 | Up | - |
| agent-frontend-1 | Up | 80→80 |

健康检查：

- `GET /healthz` → `{"status":"ok"}`
- `GET /readyz` → `{"status":"ready"}`（含数据库连通性检查）

## 2. 压测（Locust，100 用户 / 60 秒）

场景：登录、建单（128 元无凭证）、列表批量查询、详情、审批入队；
审批 409 按业务预期冲突处理，不计为系统失败。

| 指标 | 实测 | 工单合格线 | 结论 |
| --- | --- | --- | --- |
| QPS | 370（22,244 请求/60s） | >= 200 | 达标 |
| P95 延迟 | 410ms | < 300ms | **未达标** |
| 错误率 | 0%（0 失败） | < 0.1% | 达标 |
| 中位延迟 | 230ms | - | - |

分项（主要接口）：

| 接口 | req/s | 平均(ms) | 失败 |
| --- | --- | --- | --- |
| POST /api/auth/login | 1.67 | 157 | 0 |
| GET /api/tickets | 220.02 | 237 | 0 |
| POST /api/tickets | 36.82 | 363 | 0 |
| GET /healthz | - | P95 170ms | 0 |

说明：

- 首轮对单进程本地 API 压测出现大量 500（SQLAlchemy `QueuePool limit reached`），
  即单进程 10+5 连接池无法支撑 100 并发；改为 compose 4-worker API 后 0 错误。
- P95 410ms 未达 300ms 目标。基线对比：早期 50 用户/30 秒压测 P95 260ms。
  优化建议：增加 API worker 数量、提升连接池/加 PgBouncer、列表接口分页缓存。
- 原始数据：`docs/evidence/locust-run.txt`、`docs/evidence/locust-report.html`。

## 3. 容灾演练（强杀自愈）

容器均配置 `restart: unless-stopped`。

### 3.1 `docker kill` 语义实测

`docker kill agent-api-1` 后容器保持 Exited(137)、`RestartCount=0`——Docker 将
`kill`/`stop` 视为“显式停止”，重启策略按官方语义不触发（对 api/worker/frontend 均一致）。

### 3.2 崩溃退出自动重启实测

独立容器 `--restart unless-stopped` + 进程退出码 1：6 秒内自动重启 6 次
（`RestartCount=6`），证明守护进程对“非显式停止”的崩溃退出会按策略自动拉起。

### 3.3 服务恢复时间

`docker start agent-api-1` 后到 `healthz 200`：**687ms**；
容器从启动到可服务在 5 秒目标内。

结论：重启策略已配置且对真实崩溃生效；`docker kill` 属显式停止语义，不适用自动重启。

## 4. 资源观测（压测/积压处理期间）

| 容器 | CPU | 内存 |
| --- | --- | --- |
| agent-worker-1 | 35% | 125 MiB |
| agent-api-1 | 0.6% | 290 MiB |

## 5. 沙箱说明

沙箱相关（CubeSandbox/OfficeCLI/逃逸测试）已按执行人决策推迟，不在本期验收；
详见 `docs/design.md` 1.1 与 `docs/implementation-plan.md`。
