# 客诉舆情退赔决策系统 —— MVP 最小闭环设计规格说明书

> 日期：2026-08-17
> 阶段：任务一（需求分析、前后端架构设计与任务拆解）
> 范围：MVP 最小闭环（两大核心场景），其余留待任务二迭代

---

## 1. 产品定位与目标

### 1.1 背景

旧电商退款模块是 if-else 硬编码规则引擎（仅判断退款金额与是否发货）。随着多渠道客诉增加，出现大量「恶意退款 / 薅羊毛」事件，且用户上传的凭证（破损照片、快递单 OCR、聊天截图）无法自动识别，人工客服审核压力大，客服主管看不到多 Agent 决策链路与「人工审批挂起」节点状态。

### 1.2 目标

将旧系统重构为「多 Agent 协同的客诉舆情退赔决策系统」：

- 前端现代化 Dashboard 工作台：实时展示 Agent 状态流转图、客诉详情、凭证 OCR 识别结果、舆情风险报告，提供一键审批 / 拒绝的 Human-in-the-loop 界面。
- 后端多 Agent 决策流：OCR 识别 + 舆情风控 + 金额决策协同，自动分流「秒退」与「人工审批」。

### 1.3 MVP 范围（本次锁定）

1. 用户模块：客服 / 主管登录、JWT 鉴权、角色与审批权限控制。
2. 决策流模块：基于 LangGraph 的多 Agent 协作流（Intake、OCR/Evidence、Fraud/风控、Sentiment/舆情、Decision/金额决策 + HumanReview 人工节点）。
3. 流转控制：三态流转（Running → Suspended → Completed），挂起态用 Redis 序列化图上下文。
4. 数据防重：前端提交审批防重（X-Idempotency-Key + Redis 分布式锁）。
5. 大屏展示：Agent 执行路径、OCR 识别文字、舆情风险分。
6. 打包压测：Docker Compose 容器化、Locust 压测自证。

### 1.4 两大核心场景（MVP 验收主线）

- **场景一（超 300 元挂起转人工）**：金额 350 元，上传破损发票图片 → Intake → OCR 渲染文字 → 金额超限判定 HUMAN_REVIEW → HumanReview 节点挂起，工单 SUSPENDED，退款安全挂起 → 主管输入「情况属实，批准退款」点击 APPROVE → 唤醒状态机 → 终态 APPROVED / COMPLETED。
- **场景二（低金额无风险秒退）**：金额 128 元，上传清晰商品图 → 风控欺诈分 20（低风险）、舆情评分 LOW → 自动退款，全程无需人工 → 终态 COMPLETED。

---

## 2. 技术选型（已决策）

| 层 | 选型 | 决策依据 |
| --- | --- | --- |
| 后端 | Python 3.12 + FastAPI | 工单指定，异步高性能 |
| 决策流 | LangGraph（含 `langgraph-checkpoint-redis`） | 工单指定，原生 interrupt/resume |
| 队列 | Redis Streams（消费组） | 工单指定生产者-消费者模式 |
| 缓存/锁/状态 | Redis 7 | Checkpointer + 分布式锁 + 幂等键 |
| 数据库 | PostgreSQL 15+ | 工单截图暗示 |
| OCR | PaddleOCR（本地，PP-OCRv5 mobile det/rec） | 工单红线「模型本地部署推理」 |
| LLM | 云端 DeepSeek（OpenAI 兼容接口） | 本地 OCR + 云端 LLM 决策 |
| 前端 | React 18 + Vite + TS + AntD + ECharts | 现代化 Dashboard + 大屏流转图 |
| 部署 | Docker Compose（api / worker / redis / postgres / frontend） | 工单指定 |
| 压测 | Locust | 工单指定 |

---

## 3. 总体架构

```
┌──────────────┐      HTTPS/JSON        ┌──────────────────────────┐
│ 前端 React+AntD│ ────────────────────▶ │  FastAPI (API 服务)        │
│ +ECharts 大屏 │                        │  · 登录/JWT 签发           │
│  · 工单列表   │ ◀──────────────────── │  · RBAC 权限 (客服/主管)     │
│  · Agent流转图 │   SSE 状态推送(降级轮询)  │  · 幂等防重 + 写 Streams    │
│  · 审批面板   │                        └───────────┬──────────────┘
└──────────────┘                                     │ XADD
                                                     ▼
                                          ┌──────────────────────────┐
                                          │        Redis             │
                                          │ · Streams (任务队列)      │
                                          │ · Checkpointer (图状态)  │
                                          │ · 分布式锁 / 幂等键       │
                                          └───────────┬──────────────┘
                                                      │ XREADGROUP 消费
                                                      ▼
┌──────────────┐     本地推理      ┌──────────────────────────┐
│ 云端 LLM      │ ◀─────────────── │  Worker (独立进程)        │
│  DeepSeek    │   风控/舆情/金额  │  · 跑 LangGraph 决策流     │
└──────────────┘                  │  · 调 PaddleOCR (本地)     │
┌──────────────┐     图片识别      │  · 挂起时写 checkpoint    │
│  PaddleOCR   │ ◀─────────────── │                          │
│  (本地)      │                  └───────────┬──────────────┘
└──────────────┘                             │ SQL
                                             ▼
                                   ┌──────────────────────────┐
                                   │     PostgreSQL           │
                                   │ users/tickets/approvals/ │
                                   │ agent_traces             │
                                   └──────────────────────────┘
```

---

## 4. 数据流（生产者-消费者异步长任务）

```
客服提交申请 → FastAPI 校验 JWT + 幂等检查
            → 写 DB (ticket: RUNNING)
            → XADD 写入 Redis Streams
            → 返回 {ticket_id, status:RUNNING} (202)
                                        ↓
Worker XREADGROUP 消费 → 加载 LangGraph(Redis Checkpointer)
     → Intake → OCR → Fraud → Sentiment → Decision
     → 更新 ticket 状态 + agent_traces（大屏数据源）
```

---

## 5. 三态状态机

| 状态 | 含义 | 触发 |
| --- | --- | --- |
| `RUNNING` | Worker 正在执行 Agent 链 | 提交后 |
| `SUSPENDED` | 命中人工审批，图已挂起，checkpoint 落 Redis | 金额>300 或 高风险/低置信度 |
| `COMPLETED` | 终态 | `AUTO_REFUNDED` / `APPROVED` / `REJECTED` |

---

## 6. 多 Agent 决策流设计

### 6.1 Agent 职责划分

> 命名对齐：工单「四大 Agent（Intake/Evidence/Fraud/Sentiment）」与 MVP「OCR/舆情风控/金额决策」为同一批 Agent 的两种叫法，统一为 5 逻辑 Agent + 1 人工节点。

| Agent | 职责 | 实现 |
| --- | --- | --- |
| **Intake** | 解析工单、规范化字段、预判金额路由 | 规则 + LLM 兜底 |
| **OCR / Evidence** | 本地 PaddleOCR 识别凭证图片 → 结构化字段 + 置信度 | PaddleOCR |
| **Fraud / 风控** | 结合 OCR + 金额评估欺诈分 0-100 | 云端 LLM |
| **Sentiment / 舆情** | 评估舆情等级 LOW / MEDIUM / HIGH | 云端 LLM |
| **Decision / 金额决策** | 汇总输出决策：AUTO_REFUND / HUMAN_REVIEW / REJECT | 规则引擎 |
| **HumanReview** | 人工审批断点（interrupt） | LangGraph interrupt |

### 6.2 LangGraph 图结构

```
START → Intake → OCR → Fraud → Sentiment → Decision
                                              │
                         ┌────────────────────┼────────────────────┐
                    AUTO_REFUND         HUMAN_REVIEW          (REJECT)
                         │               interrupt() 挂起          │
                         ▼                    │                    ▼
                      END            主管 APPROVE/REJECT        END(REJECTED)
                                            resume 唤醒
                                              │
                                    APPROVED / REJECTED → END
```

### 6.3 核心决策规则（已锁定）

```
IF 金额 > 300                  → HUMAN_REVIEW（挂起）
ELIF 欺诈分 < 50 AND 舆情==LOW  → AUTO_REFUND（秒退，直接 Completed）
ELSE                          → HUMAN_REVIEW（挂起）
```

### 6.4 挂起与恢复

- 挂起：`Decision` 判定 HUMAN_REVIEW → 进入 HumanReview 节点调用 `interrupt()`，图状态由 Redis Checkpointer 序列化落 Redis，`ticket.status = SUSPENDED`。
- 恢复：主管审批 → FastAPI 校验权限 + 分布式锁 → `graph.invoke(Command(resume={"action": "APPROVE"}))` 唤醒，Worker 继续走剩余边 → 终态。

---

## 7. 数据模型（PostgreSQL）

```sql
users         (id PK, username UNIQUE, password_hash, role ENUM('cs','sv'), created_at)
tickets       (id PK, ticket_no UNIQUE, user_id FK, amount NUMERIC,
               image_paths JSONB,            -- 凭证图片
               ocr_text TEXT, ocr_confidence NUMERIC,
               fraud_score INT, sentiment TEXT,      -- LOW/MEDIUM/HIGH
               status ENUM('RUNNING','SUSPENDED','COMPLETED'),
               decision ENUM('PENDING','AUTO_REFUNDED','APPROVED','REJECTED'),
               thread_id TEXT,               -- LangGraph checkpoint 线程
               idempotency_key TEXT,
               created_at, updated_at)
approvals     (id PK, ticket_id FK, reviewer_id FK,
               action ENUM('APPROVE','REJECT'), comment TEXT, created_at)
agent_traces  (id PK, ticket_id FK, agent_name TEXT,
               status ENUM('RUNNING','SUCCESS','FAILED','SUSPENDED'),
               input_summary TEXT, output_summary TEXT,
               started_at, ended_at)         -- 大屏流转图数据源
```

---

## 8. 缓存与防重（Redis key 设计）

| Key | 用途 | 机制 |
| --- | --- | --- |
| `idem:{user_id}:{idempotency_key}` | 提交防重 | SET NX，TTL 24h，已存在返回首次工单 ID |
| `lock:approve:{ticket_id}` | 审批并发锁 | SET NX PX 10000，第二人拿不到锁返回 409 |
| `lock:status:{ticket_id}` | 状态更新原子化 | Lua 脚本 CAS 更新，防 Lost Update |
| `checkpoint:{thread_id}:*` | 挂起图状态 | Redis Checkpointer 自动管理 |
| `stream:tickets` | 异步任务队列 | 消费组 `worker-group` |

---

## 9. 接口设计（RBAC）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | 公开 | 登录，返回 `{access_token}` |
| POST | `/api/tickets` | 客服/主管 | 提交申请，Header 带 `X-Idempotency-Key` |
| GET | `/api/tickets` | 客服/主管 | 工单列表 |
| GET | `/api/tickets/{id}` | 客服/主管 | 详情（OCR/风控/舆情/轨迹/状态） |
| POST | `/api/tickets/{id}/approve` | **仅主管** | `{action, comment}` 唤醒挂起图 |
| GET | `/api/tickets/{id}/events` | 客服/主管 | SSE 状态推送（大屏实时刷新，不支持 SSE 时降级为前端轮询） |

- JWT payload：`{sub, role, exp}`；`require_role("sv")` 装饰器拦截非主管审批。
- 客服：建单、查看；主管：全部 + 审批。

---

## 10. 边界情况（if-then）

| 场景 | 处理 |
| --- | --- |
| OCR 置信度 < 0.6 | 标记 `OCR_LOW_CONF` → 强制 HUMAN_REVIEW |
| 风控/舆情 LLM 超时/5xx | 降级：保守转 HUMAN_REVIEW（宁挂勿错退） |
| LLM Output Parse 失败 | 重试 1 次 → 仍失败转 HUMAN_REVIEW |
| 同一幂等键重复提交 | 返回首次创建的工单 ID，不重复建单 |
| 两个主管并发审批同一单 | 锁拒绝第二个，返回 409 |
| 挂起后 checkpoint 丢失 | ticket 标记 `FAILED`，触发重试/告警 |

---

## 11. 测试策略

- 单元：决策规则、幂等键、RBAC 装饰器、图状态序列化。
- 集成：两大场景端到端（350 元挂起→审批→APPROVED；128 元秒退→COMPLETED）。
- 防重：并发提交、并发审批。
- 压测：Locust（QPS≥200 / P95<300ms / 错误率<0.1%）。

---

## 12. WBS 拆解（1 人 1 周 = 7 人日）

| 阶段 | 任务 | 人日 |
| --- | --- | --- |
| 任务一 | 需求分析 + 架构设计 + 三方对齐 + 剖析手册 | 1.5 |
| 任务二 | 后端（用户/决策流/流转/防重）+ 前端 Dashboard + 两大场景联调 | 3.0 |
| 任务三 | Docker Compose + 健康检查/自启动 + Locust 压测 | 2.5 |
| 任务四 | AI 代码审查报告 + 面试 QA 库 | 1.0 |

> 任务二内部的细粒度任务清单在实现计划（writing-plans）阶段展开。

---

## 13. 关键决策记录（三方对齐沉淀）

| 决策点 | 结论 | 理由 |
| --- | --- | --- |
| 交付粒度 | 锁定 MVP 最小闭环 | 快速锁规格，其余任务二迭代 |
| 模型部署 | 本地 PaddleOCR + 云端 DeepSeek LLM | OCR 符合工单红线，LLM 走云端降延迟 |
| 前端栈 | React + AntD + ECharts | 后台组件 + 大屏流转图 |
| 决策规则 | 300 元 / 欺诈分<50 / 舆情=LOW 秒退 | 匹配工单场景二，其余挂起 |
| 挂起机制 | LangGraph 原生 interrupt + Redis Checkpointer | 少写状态机代码，贴合工单原话 |
| 异步架构 | FastAPI + Redis Streams + Worker | 解耦、可扩展，工单明确要求 |
| 数据库 | PostgreSQL | 工单截图暗示 |
| LLM 提供方 | DeepSeek（OpenAI 兼容） | 省事，Qwen 可替换 |

---

## 14. 非功能需求

- 性能：核心接口 QPS≥200、P95<300ms、错误率<0.1%（Locust 验收）。
- 容灾：`docker kill` 后端/Worker 后 5 秒内健康检查自拉起。
- 安全：密码哈希存储；JWT 过期；审批仅主管；提交防重与并发锁防资损。
- 可观测：agent_traces 支撑大屏，Prometheus/Grafana 预留（任务三）。
