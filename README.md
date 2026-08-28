# 客诉舆情退赔决策系统（MVP）

> 多 Agent 协同的客诉退赔辅助决策系统：客服提交工单后，系统自动执行「凭证识别（本地 OCR）→ 风险分析 →
> 舆情分析 → 金额决策」链路，对低风险工单自动退赔，对高风险/不确定工单挂起转主管人工审批，审批后从断点恢复。

---

## 目录

1. [核心特性](#核心特性)
2. [系统架构](#系统架构)
3. [技术栈](#技术栈)
4. [目录结构](#目录结构)
5. [快速开始](#快速开始)
6. [本地算法模型](#本地算法模型)
7. [LLM 接入](#llm-接入)
8. [测试与验收](#测试与验收)
9. [Docker 部署与压测](#docker-部署与压测)
10. [三方对齐 P0 实现清单](#三方对齐-p0-实现清单)

---

## 核心特性

- **多 Agent 自动决策**：Intake → OCR（本地 PaddleOCR）→ 风控 → 舆情 → 金额决策的完整链路。
- **三态流转 + 挂起恢复**：`RUNNING → SUSPENDED → COMPLETED`；挂起用 LangGraph 原生 `interrupt()` + Redis Checkpointer，恢复用 `Command(resume=...)`，**禁止手工 pickle**。
- **先保守、后自动（宁挂勿错退）**：OCR 低置信度、LLM 超时/非法输出一律转人工，绝不自动放行。
- **防资损**：建单幂等（SET NX + DB 兜底）+ 审批分布式锁（**随机 token + Lua 比较后删除**）+ DB 条件更新。
- **失败语义可审计**：Worker 不可恢复异常落库 `COMPLETED + FAILED + error_code` 后再 XACK；checkpoint 缺失 → `FAILED + CHECKPOINT_NOT_FOUND`。
- **角色化控制台与可观测**：客服仅可查看自己创建的申请；主管默认进入待处理优先的实时监控，可处理审批并查看数据大屏。监控页每 5 秒轮询更新异常、待审批和处理中订单。

## 系统架构

```text
┌───────────────────────────── React + TypeScript + AntD + ECharts ──────────────────────────────┐
│  登录 / 角色化导航 / 工单创建 / 图片上传 / Agent 流转图 / 审批面板 / 实时监控 / 流程总览 / 大屏 │
└──────────────────────────────────────┬────────────────────────────────────────────────────────┘
                                       │ HTTP：JWT、X-Idempotency-Key、SSE
┌──────────────────────────────────────▼────────────────────────────────────────────────────────┐
│  FastAPI API：鉴权 + RBAC / 工单与文件 API / 幂等 / 审批锁（token+Lua）/ SSE 事件             │
└──────────────┬──────────────────────────────┬──────────────────────────────────────────────────┘
               │ SQL                          │ XADD（Redis Streams）
┌──────────────▼──────────────┐   ┌───────────▼──────────────────────────────────────────────────┐
│  PostgreSQL（业务事实）      │   │  Redis：Streams 队列 / 幂等键 / 审批锁 / Checkpointer         │
│  users / tickets /           │   └───────────┬──────────────────────────────────────────────────┘
│  approvals / agent_traces    │               │ XREADGROUP
└──────────────────────────────┘   ┌───────────▼──────────────────────────────────────────────────┐
                                   │  Worker（可横向扩容）：LangGraph 决策图                       │
                                   │  Intake → OCR → 风控 → 舆情 → 决策 →（人工审批 interrupt）   │
                                   └───────┬──────────────────┬───────────────────────────────────┘
                                           │ OCR（本地推理）   │ LLM（OpenAI 兼容，DeepSeek/Mock）
                                      PaddleOCR（自动下载模型） DeepSeek 或本地 Mock/Stub
```

## 技术栈

| 层次 | 选型 |
| --- | --- |
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0 + Pydantic v2 |
| 决策流 | LangGraph + Checkpointer（默认 PostgreSQL；`CHECKPOINTER_BACKEND=redis` 可切 Redis，需 RedisJSON） |
| 队列 | Redis Streams（XADD / XREADGROUP / XACK） |
| OCR | 本地 PaddleOCR 2.x（`paddlepaddle==2.6.2` + `paddleocr==2.9.1`） |
| LLM | OpenAI 兼容适配器：DeepSeek（`deepseek-chat`）或本地 Mock |
| 认证 | JWT（bcrypt 密码哈希，2 小时） |
| 前端 | React 18 + TypeScript + Vite + AntD + ECharts |
| 部署压测 | Docker Compose + Locust |

## 目录结构

```
backend/
├── app/
│   ├── config.py              # 配置（DB/Redis/JWT/LLM/OCR/阈值/Streams）
│   ├── db.py / models.py      # SQLAlchemy 引擎与模型（含 error_code）
│   ├── security.py / deps.py  # JWT + bcrypt + RBAC
│   ├── idempotency.py         # 幂等键（SET NX）
│   ├── locks.py               # 审批分布式锁（随机 token + Lua 比较删除）
│   ├── storage.py             # 上传文件落盘（MIME/魔数校验 + sha256）
│   ├── agents/                # LangGraph 决策流（state/nodes/graph/ocr/llm/decision_rules）
│   ├── routers/               # auth / tickets（含 SSE）/ files
│   ├── worker/consumer.py     # Redis Streams 消费者 + Checkpointer + FAILED 语义
│   └── main.py                # 入口（建表 + 种子用户 + healthz/readyz）
├── tests/                     # 36 项单测（决策规则/JWT/幂等/锁/图/API/角色权限）
├── requirements.txt           # 核心依赖
├── requirements-ocr.txt       # OCR 重型依赖（单独安装）
└── Dockerfile
frontend/
├── src/
│   ├── pages/                 # Login / Dashboard / MyTickets / Monitor / ProcessOverview / TicketDetail / Screen
│   ├── components/            # AppShell / StatusLegend / FlowCanvas（ECharts 流转图）/ ApprovePanel
│   ├── types/auth.ts          # JWT 角色解析（仅用于前端导航体验）
│   └── api/client.ts          # axios 封装 + token 注入
├── Dockerfile / nginx.conf
scripts/
├── scenario_e2e.py            # 两大核心场景 + 并发审批联调脚本
├── test_unit_standalone.py    # 单元测试独立脚本（不依赖 pytest）
└── test_interface_idempotency.py  # 接口防重测试独立脚本
docker-compose.yml             # postgres + redis + api + worker + frontend
locustfile.py                  # 压测脚本
```

## 快速开始

### 本地开发（后端）

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-ocr.txt      # PaddleOCR 本地推理
# 启动 PostgreSQL + Redis（Streams/幂等/锁；Checkpointer 默认走 PostgreSQL）
docker compose up -d postgres redis
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/refund
export REDIS_URL=redis://localhost:6379/0
export LLM_PROVIDER=mock                 # 无 DeepSeek 密钥时用本地 Mock
uvicorn app.main:app --port 8000
# 另开终端启动 Worker
python -m app.worker.consumer
```

### 前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173（代理 /api → :8001）
```

### 演示账号（密码统一 `secret123`）

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `cs1` | `secret123` | 客服（提交工单） |
| `sv1` | `secret123` | 主管（审批） |
| `customer_service_01` | `secret123` | 客服（specs 命名） |
| `supervisor_01` | `secret123` | 主管（specs 命名） |

> 任一命名均可登录；`specs/quickstart.md` 的登录示例使用 `supervisor_01`。
>
> - 客服登录后默认进入“我的申请”，后端仅返回其本人创建的工单；
> - 主管登录后默认进入“实时监控”，可查看全部最近 100 条工单并审批待处理订单。

### 登录后页面

| 页面 | 路径 | 适用角色 | 说明 |
| --- | --- | --- | --- |
| 我的申请 | `/my-tickets` | 客服 | 查看自己创建的退款申请并新建申请。 |
| 实时监控 | `/monitor` | 主管 | 每 5 秒刷新异常、待审批、处理中订单及优先处理队列。 |
| 退款工作台 | `/workspace` | 主管 | 查看全部最近 100 条退款工单。 |
| 退款流程总览 | `/process` | 全部 | 说明提交、OCR、风控、舆情、决策与处理结果的标准链路。 |
| 数据大屏 | `/screen` | 主管 | 查看退款统计和聚合图表。 |

## 本地算法模型

- **OCR**：本地 PaddleOCR 推理引擎，首次调用自动下载 PP-OCRv4 中文模型（约 20MB），之后完全离线推理。
  验证：识别「退款申请单」「订单号20260817」，平均置信度 0.9982。
- **LLM/风控**：OpenAI 兼容客户端适配器，`LLM_PROVIDER=deepseek` 接 DeepSeek API；`LLM_PROVIDER=mock` 走本地确定性 Stub（含欺诈关键词检测、舆情分级），单测与无密钥环境可用。

> **注意**：PaddleOCR 3.x + paddlepaddle 3.x 在 Windows 上存在 onednn/PIR 执行器缺陷，本项目锁定已验证的 2.x 组合。

## LLM 接入

```bash
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-xxx
export DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
export DEEPSEEK_MODEL=deepseek-chat
```

LLM 异常兜底：超时/非法输出 → 重试 1 次 → 保守兜底（Fraud=100 / Sentiment=HIGH）→ 决策层强制人工。

## 测试与验收

```bash
cd backend
pytest tests/ -v        # 36 passed，1 项真实 Redis 锁测试在无 Redis 环境跳过
```

| 测试 | 覆盖 |
| --- | --- |
| `test_decision_rules` | 决策规则全部边界（金额=300/置信度=0.60/欺诈=50/舆情非 LOW） |
| `test_locks` | 锁互斥 + **旧 token 释放不误删新锁（竞态修复）** + Lua 路径断言 |
| `test_graph` | 自动退款 / interrupt 挂起 / Command(resume) 恢复 / REJECT |
| `test_*_api` | 登录 / 建单幂等 / RBAC 越权 / 工单角色隔离 / 审批恢复 / 健康检查 |

### 独立运行脚本使用指南（不依赖 pytest）

三个脚本均**直接在终端运行**（无需 pytest 框架），但需注意：
- 必须使用项目 venv 的 Python（`.\.venv\Scripts\python.exe`），脚本依赖 fakeredis/PIL 等已装入 venv；
- 必须在**项目根目录**下执行；
- 脚本 ②③ 需要后端已启动，脚本 ① 零依赖、最快。

| 脚本 | 用途 | 前置 | 一句话运行 |
| --- | --- | --- | --- |
| `scripts/test_unit_standalone.py` | 核心单元逻辑：决策规则 / 认证安全 / 幂等键 / 分布式锁 | 无 | `.\.venv\Scripts\python.exe scripts\test_unit_standalone.py` |
| `scripts/test_interface_idempotency.py` | 接口 `X-Idempotency-Key` 防重：同 Key 重放 / 不同 Key / 并发 | 后端已启动 | `.\.venv\Scripts\python.exe scripts\test_interface_idempotency.py [BASE_URL]` |
| `scripts/scenario_e2e.py` | 两大核心场景 + 并发审批联调（S1 人工审批 / S2 自动退款 / LOCK） | 后端 + worker | `.\.venv\Scripts\python.exe scripts\scenario_e2e.py [BASE_URL]` |

#### ① 环境准备（一次性）

```powershell
cd "D:\Claude Code\舆情多Agent"
python -m venv .venv                                    # 已存在可跳过
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-ocr.txt   # PaddleOCR 本地推理
```

启动后端（脚本 ②③ 需要；脚本 ① 不需要）：

```powershell
docker compose up -d --build       # 一键起全栈：postgres / redis / api / worker / frontend
curl http://localhost:8001/healthz # Docker 后端返回 ok 即就绪；本地 Uvicorn 仍使用 8000
```

#### ② 脚本①：单元测试（最快，无需后端）

验证 4 组核心逻辑，不访问任何服务，秒级出结果：

```powershell
.\.venv\Scripts\python.exe scripts\test_unit_standalone.py
```

预期输出（4 组全 PASS）：

```
===== 核心单元逻辑独立测试（不依赖 pytest） =====
[1/4] 决策规则 decide()        → [PASS]
[2/4] 认证安全 security        → [PASS]
[3/4] 幂等键 idempotency       → [PASS]
[4/4] 分布式锁 locks           → [PASS]
===== 结果：4 passed, 0 failed =====
```

#### ③ 脚本②：接口防重（需后端）

向真实 API 提交工单验证 `X-Idempotency-Key` 防重，共 4 个用例，**会在系统里创建少量测试工单**（金额 128 的即为测试数据）：

```powershell
.\.venv\Scripts\python.exe scripts\test_interface_idempotency.py
# 后端不在默认 8000 端口时，追加地址参数：
.\.venv\Scripts\python.exe scripts\test_interface_idempotency.py http://localhost:8001
```

预期输出（4 个用例全 PASS）：

```
===== 接口防重（X-Idempotency-Key）测试 @ http://localhost:8001 =====
[login] cs1 OK
[T1] 同 Key 重放 → 同一工单        [PASS] 证据: Key=it-xxx-a → ticket_id=10414（重放返回同单，金额保持 128.0）
[T2] 不同 Key → 不同工单           [PASS] 证据: Key=it-xxx-b1 → 10415, Key=it-xxx-b2 → 10416
[T3] 无 Key → 不同工单             [PASS] 证据: 无 Key 两次 → 10417 / 10418
[T4] 并发不同 Key → 互不相同        [PASS] 证据: 并发 5 个不同 Key → 全部 200，工单互不相同 [10419, ...]
===== 结果：4 passed, 0 failed =====
```

#### ④ 脚本③：两大场景联调（需后端 + worker）

跑两个核心业务场景 + 并发审批竞态，全程真实 HTTP + 真实本地 OCR，约 40 秒：

```powershell
.\.venv\Scripts\python.exe scripts\scenario_e2e.py
```

预期输出：

```
[login] OK
[S1] <tid> 挂起 [OK]  OCR置信度=0.99x  OCR='破损商品退款申请 金额350.00元'
[S1] <tid> APPROVED [OK]
[S2] <tid> AUTO_REFUNDED [OK]  (OCR置信度=0.99x)
[LOCK] 并发审批 {409:5, 200:1} [OK]（1 成功 + 5 冲突）
=== 全部场景通过 ===
```

#### ⑤ 常见问题排查

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| 中文输出乱码 | Windows 控制台默认 GBK 编码 | 运行前先执行 `$env:PYTHONIOENCODING="utf-8"`，或 `chcp 65001` |
| `ModuleNotFoundError: fakeredis` 等 | 用错了 Python（系统 Python 而非 venv） | 必须用 `.\.venv\Scripts\python.exe` |
| 登录失败 / `Connection refused` | 后端未启动 | `docker compose up -d api worker` 后再跑 |
| 后端端口不是 8000 | 环境差异 | 脚本追加 `http://IP:端口` 参数 |
| 脚本 ②③ 后页面多出工单 | 脚本创建的测试数据 | 属正常现象，金额 128 / 350 的即测试工单 |

## Docker 部署与压测

```bash
docker compose up -d --build          # 一键启动全栈
# 前端 http://localhost:80    Docker API http://localhost:8001/docs
locust -f locustfile.py --headless -u 100 -r 20 -t 60s --host http://localhost:8001
```

> Checkpointer 默认走 PostgreSQL（`CHECKPOINTER_BACKEND=postgres`），零额外依赖。
> 若改用 Redis Checkpointer（`CHECKPOINTER_BACKEND=redis`），需 Redis 带 RedisJSON 模块（如 `redis/redis-stack-server`）。

## 三方对齐 P0 实现清单

| 项 | 要求 | 实现 |
| --- | --- | --- |
| A-01 | 锁释放随机 token + Lua 比较后删除，禁无条件 DEL | `locks.py`：`secrets.token_urlsafe(32)` + `redis.eval` Lua 比较删除，真实 Redis 验证通过 |
| A-02 | Decision 含 `FAILED`，Ticket 含 `error_code/error_message` | `models.py` 已补齐 |
| A-03 | Worker 不可恢复异常先落 `FAILED + error_code` 再 XACK | `consumer.py` `mark_failed()` 后 `xack` |
| A-04 | `decide` 统一 4 参（含 `ocr_confidence`） | `decision_rules.decide(amount, ocr_confidence, fraud_score, sentiment)` |
| A-05 | SSE + 轮询降级 | 前端 `EventSource` + 断线 2s 轮询 |
| A-06 | 开发 create_all / 生产 Alembic（记录口径） | 开发 `Base.metadata.create_all` |
| A-07 | checkpoint 缺失兜底 `FAILED + CHECKPOINT_NOT_FOUND` | `consumer.py` 恢复路径校验 |
