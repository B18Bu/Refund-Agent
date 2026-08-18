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
- **可观测**：React + AntD + ECharts 工作台与实时大屏，SSE 实时推送 + 断线轮询降级。

## 系统架构

```text
┌───────────────────────────── React + TypeScript + AntD + ECharts ──────────────────────────────┐
│  登录 / 工单创建 / 图片上传 / Agent 流转图 / OCR 与风险结果 / 审批面板 / 实时大屏              │
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
├── tests/                     # 30 项单测（决策规则/JWT/幂等/锁/图/API）
├── requirements.txt           # 核心依赖
├── requirements-ocr.txt       # OCR 重型依赖（单独安装）
└── Dockerfile
frontend/
├── src/
│   ├── pages/                 # Login / Dashboard / TicketDetail / Screen（大屏）
│   ├── components/            # FlowCanvas（ECharts 流转图）/ ApprovePanel
│   └── api/client.ts          # axios 封装 + token 注入
├── Dockerfile / nginx.conf
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
npm run dev        # http://localhost:5173（代理 /api → :8000）
```

### 演示账号（密码统一 `secret123`）

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `cs1` | `secret123` | 客服（提交工单） |
| `sv1` | `secret123` | 主管（审批） |
| `customer_service_01` | `secret123` | 客服（specs 命名） |
| `supervisor_01` | `secret123` | 主管（specs 命名） |

> 任一命名均可登录；`specs/quickstart.md` 的登录示例使用 `supervisor_01`。

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
pytest tests/ -v        # 30 passed（1 项真实 Redis 锁测试在无 Redis 环境跳过）
```

| 测试 | 覆盖 |
| --- | --- |
| `test_decision_rules` | 决策规则全部边界（金额=300/置信度=0.60/欺诈=50/舆情非 LOW） |
| `test_locks` | 锁互斥 + **旧 token 释放不误删新锁（竞态修复）** + Lua 路径断言 |
| `test_graph` | 自动退款 / interrupt 挂起 / Command(resume) 恢复 / REJECT |
| `test_*_api` | 登录 / 建单幂等 / RBAC 越权 / 健康检查 |

## Docker 部署与压测

```bash
docker compose up -d --build          # 一键启动全栈
# 前端 http://localhost:80    API http://localhost:8000/docs
locust -f locustfile.py --headless -u 100 -r 20 -t 60s --host http://localhost:8000
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
