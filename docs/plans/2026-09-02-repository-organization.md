# 仓库目录规整实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将部署配置、受管理文档、样例与压测入口分层归档，同时保持 Docker、测试与本地启动命令可用。

**架构：** 保留源码、运行数据与评测目录；使用 `git mv` 迁移已跟踪文件，使用相对路径适配新的 Compose 位置。`Makefile` 成为 Compose 的稳定入口，本地临时文件只补充忽略规则且不移动。

**技术栈：** Git、Docker Compose、Make、PowerShell、pytest、Node.js、Vite。

---

### 任务 1：建立稳定部署入口并迁移 Compose

**文件：**
- 创建：`deploy/compose/docker-compose.yml`
- 修改：`Makefile`、`README.md`
- 删除：`docker-compose.yml`（通过 Git 重命名）

- [ ] **步骤 1：编写迁移前失败检查**

运行：`Test-Path deploy/compose/docker-compose.yml`

预期：`False`，证明新部署入口尚未创建。

- [ ] **步骤 2：迁移并修正 Compose 路径**

运行：`New-Item -ItemType Directory -Force deploy/compose; git mv docker-compose.yml deploy/compose/docker-compose.yml`。

在新 Compose 文件中将 API/Worker 的 `build: ./backend` 改为 `build: ../../backend`；将前端 `build: ./frontend` 改为 `build: ../../frontend`；将 API 报告挂载 `./artifacts:/app/artifacts:ro` 改为 `../../artifacts:/app/artifacts:ro`。服务名、端口、命名卷、环境变量和 OCR 主机路径不变。

将 `Makefile` 替换为以下稳定入口：

```make
COMPOSE_FILE := deploy/compose/docker-compose.yml
COMPOSE := docker compose --env-file .env -f $(COMPOSE_FILE)
.PHONY: check test compile frontend-build up down build ps logs
check: compile test
compile:
	python -m compileall -q backend scripts
test:
	python -m pytest backend/tests -q
frontend-build:
	npm --prefix frontend run build
up:
	$(COMPOSE) up -d
down:
	$(COMPOSE) down
build:
	$(COMPOSE) build
ps:
	$(COMPOSE) ps
logs:
	$(COMPOSE) logs --tail=100
```

README 的目录树和 Docker 命令改为 `make up`、`make build` 或 `docker compose --env-file .env -f deploy/compose/docker-compose.yml`。

- [ ] **步骤 3：验证新部署入口通过**

运行：`docker compose --env-file .env -f deploy/compose/docker-compose.yml config; make ps`

预期：Compose 成功解析并可读取当前服务状态。

- [ ] **步骤 4：Commit**

运行：`git add Makefile README.md deploy/compose/docker-compose.yml; git commit -m "chore(部署): 迁移 Compose 配置入口"`。

### 任务 2：归档受管理文档、样例与压测入口

**文件：**
- 创建：`docs/guides/`、`docs/plans/`、`docs/specs/`、`docs/archive/{workorders,interviews,academic,diagnostics,task1}/`、`docs/assets/samples/`、`scripts/loadtest/`
- 修改：`README.md` 与全部引用旧文档、Compose、样例或压测路径的已跟踪文本文件

- [ ] **步骤 1：编写迁移前失败检查**

运行：`Test-Path docs/plans; Test-Path docs/specs`

预期：两个路径均为 `False`。

- [ ] **步骤 2：使用 Git 重命名归档**

执行下列映射：

```text
docs/superpowers/plans/*.md                  -> docs/plans/
docs/superpowers/specs/*.md                  -> docs/specs/
docs/CubeSandbox配置说明.md                   -> docs/guides/cubesandbox.md
docs/design.md                               -> docs/guides/architecture.md
docs/sec_spec.md                             -> docs/specs/security-gateway.md
docs/implementation-plan.md                  -> docs/plans/mvp-implementation.md
docs/workorder*-implementation-plan.md       -> docs/plans/
docs/workorder*-*tech-spec.md                -> docs/specs/
docs/workorder*-three-party-alignment.md     -> docs/archive/workorders/
docs/workorder*-testing-plan.md              -> docs/archive/workorders/
docs/workorder6-zero-trust-security-plan.md  -> docs/archive/workorders/
docs/interview-qa-*.md                       -> docs/archive/interviews/
docs/project-retrospective.md                -> docs/archive/
docs/ai-review.md, docs/deploy-report.md     -> docs/evidence/
docs/两大核心场景联调证明.md                   -> docs/evidence/scenario-e2e-proof.md
docs/多Agent 协同项目*.md                     -> docs/archive/workorders/
docs/电商客诉舆情退赔决策系统竞品调研报告.*     -> docs/archive/academic/
任务一实现/                                  -> docs/archive/task1/
工单/                                        -> docs/archive/workorders/source/
goods128.png, invoice350.png                 -> docs/assets/samples/
loadtest_report.html                         -> artifacts/local/loadtest-report.html
locustfile.py                                -> scripts/loadtest/locustfile.py
.tmp-cube-*                                  -> docs/archive/diagnostics/
```

所有移动使用 `git mv`。将 `scripts/scenario_e2e.py` 的样例路径改为 `docs/assets/samples/`；将压测文档中的入口改为 `locust -f scripts/loadtest/locustfile.py`。将所有活动代码、README、指南和现行计划中的 `docs/superpowers`、`docs/sec_spec.md`、`docs/workorder*` 与根目录 Compose 引用更新为新路径。

- [ ] **步骤 3：验证文档迁移通过**

运行：`rg -n 'docs/superpowers|docs/sec_spec.md|(^|[^/])docker-compose.yml|Path\("goods128.png"\)|Path\("invoice350.png"\)' --glob '!docs/archive/**' --glob '!frontend/node_modules/**'; git diff --summary`

预期：第一条命令没有活动代码、README、现行指南或现行计划命中；第二条主要显示 `rename`。

- [ ] **步骤 4：Commit**

先运行 `git status --short`，确认不暂存既有的 `docs/evidence/periodic-eval-report.md` 与 `scripts/scenario_e2e.py` 修改；只选择上方映射创建或重命名的精确路径暂存。运行：`git commit -m "chore(文档): 分层归档仓库资料"`。

### 任务 3：保护本地文件并完成运行验证

**文件：**
- 修改：`.gitignore`
- 测试：`backend/tests`、`frontend/tests/*.test.mjs`

- [ ] **步骤 1：编写迁移前失败检查**

运行：`git check-ignore -q bc_0WIN0DJ6VL4UY2KW_09.db; if ($LASTEXITCODE -eq 0) { throw '本地数据库已被忽略，无法证明新增规则' }`

预期：命令抛出错误，因为本地数据库尚未被忽略。

- [ ] **步骤 2：加入仅本地文件忽略规则**

在 `.gitignore` 增加：

```gitignore
# 本地代理、浏览器与数据库诊断产物
.tmp-edge-ui-diagnostic/
.tmp-cube-*
bc_*.db
artifacts/ui-check-*.png
bash.exe.stackdump
```

不忽略或移动已跟踪的安全报告；不删除 `.venv/`、`venv/`、`tmp/`、`nul` 或任何现有本地文件。

- [ ] **步骤 3：运行完整验证**

运行：

```powershell
git check-ignore bc_0WIN0DJ6VL4UY2KW_09.db artifacts/ui-check-monitor.png
docker compose --env-file .env -f deploy/compose/docker-compose.yml up -d --build api worker frontend
docker compose --env-file .env -f deploy/compose/docker-compose.yml ps
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8001/openapi.json
Invoke-WebRequest -UseBasicParsing http://127.0.0.1/login
node --test frontend/tests/*.test.mjs
npm --prefix frontend run build
docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/source/backend -e UPLOAD_DIR=/tmp/uploads -v "${PWD}:/source:ro" -w /source agent-api:latest python -m pytest backend/tests -q -p no:cacheprovider
git diff --check
```

预期：本地文件被忽略；API、Worker、前端运行；OpenAPI 与登录页返回 200；前端构建和后端测试通过；差异检查无输出。

- [ ] **步骤 4：Commit 并推送**

运行：`git add .gitignore docs/plans/2026-09-02-repository-organization.md; git commit -m "chore(仓库): 忽略本地诊断产物"; git push origin main`。

## 规格覆盖自检

- 根目录运行入口、Compose 位置和兼容路径：任务 1。
- 文档、计划、规格、工单、样例、压测与诊断文件归档：任务 2。
- 不删除本地文件、忽略规则、Docker 重建、API/前端/测试验证：任务 3。
