# 仓库目录规整设计

## 目标

降低根目录噪声，并将文档、部署配置、样例与本地输出按职责归档；不改变项目的启动方式、Docker 构建上下文、认证边界或业务代码语义。

## 目标目录

根目录保留运行与开发入口：

```text
backend/  frontend/  scripts/  docs/  artifacts/  evals/  data/  deploy/
README.md  Makefile  AGENTS.md  .env.example
```

- `deploy/compose/docker-compose.yml`：唯一 Compose 配置；`Makefile` 提供统一入口，README 只引用该入口。
- `docs/guides/`：配置与使用指南。
- `docs/plans/`：可执行实施计划。
- `docs/specs/`：设计与需求规格。
- `docs/evidence/`：验收、压测与安全证据。
- `docs/archive/`：已完成工单、课程材料、面试材料与历史说明。
- `docs/assets/samples/`：文档使用的样例图片。
- `artifacts/local/`：可再生的本地报告；安全验收报告仍保留在 `artifacts/` 以兼容运行时配置。

## 迁移边界

- 不移动 `backend/`、`frontend/`、`scripts/`、`artifacts/`、`evals/`、`data/` 或根目录 `.env`。
- 不删除文件、Docker 卷、容器、数据库或 Redis 数据。
- 根目录中未跟踪的本地数据库、截图、临时文件、虚拟环境、崩溃转储和设备诊断文件只加入 `.gitignore`，不移动也不删除。
- 只移动可通过 `git mv` 追踪的文档、样例和 Compose 配置；每次移动后更新所有文本路径引用。

## 兼容策略

- Compose 移动前，先为每个 `build`、`volumes`、环境文件和模型目录改为以新 Compose 文件为基准的正确相对路径。
- `Makefile` 增加固定 `COMPOSE_FILE := deploy/compose/docker-compose.yml`，保留当前 `make` 目标名称。
- README 的启动命令改为 `make` 目标或明确的 `docker compose -f deploy/compose/docker-compose.yml` 命令。
- 运行时读取的安全、Golden 与 DLP 证据文件保持 `artifacts/` 路径，避免更改 API 配置。

## 验收

1. `git diff --check` 无输出，所有已移动的受 Git 管理文件仍可由 Git 识别为重命名。
2. `docker compose -f deploy/compose/docker-compose.yml config` 成功解析。
3. 使用新 Compose 路径重建并启动 API、Worker、前端，不删除数据库和 Redis 卷；OpenAPI、登录页和登录接口均返回成功。
4. 前端静态测试和生产构建通过；后端完整测试通过。
5. 根目录不再保留散落的受管理文档、样例图片、Compose 文件或本地报告；本地临时文件仍在原处且已被忽略。
