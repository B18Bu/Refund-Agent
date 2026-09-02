# AI-B 最小 MVP 实现方案

> 项目：多 Agent 协同客诉舆情退赔决策系统  
> 文档角色：AI-B（工程实现视角）  
> 日期：2026-08-17  
> 状态：需求澄清完成，可作为后续编码与验收的基线

---

## 目录

1. [需求转述与 MVP 边界](#1-需求转述与-mvp-边界)
2. [关键决策与设计原则](#2-关键决策与设计原则)
3. [总体技术架构](#3-总体技术架构)
4. [核心业务流与状态机](#4-核心业务流与状态机)
5. [模块、类与接口设计](#5-模块类与接口设计)
6. [数据模型与表结构](#6-数据模型与表结构)
7. [Redis、消息与一致性设计](#7-redis消息与一致性设计)
8. [API 契约与权限控制](#8-api-契约与权限控制)
9. [大屏展示与实时更新](#9-大屏展示与实时更新)
10. [异常、边界与安全策略](#10-异常边界与安全策略)
11. [部署、压测与验收](#11-部署压测与验收)
12. [待实施前确认项](#12-待实施前确认项)

---

## 1. 需求转述与 MVP 边界

### 1.1 用自己的话转述需求

要建设一个面向客服与主管的**客诉退赔辅助决策系统**。客服上传客诉凭证并提交工单后，系统通过 LangGraph 编排 OCR、舆情风控和金额决策等 Agent，在后台异步完成分析：

- 对凭证图片做本地 OCR，输出文字与识别置信度；
- 基于工单材料做欺诈/风险打分和舆情等级判断；
- 按确定性金额规则给出“自动通过”或“转主管人工审批”的结果；
- 对需要人工处理的工单，持久化 LangGraph 上下文并进入挂起状态；主管审批后从断点恢复执行；
- 前端工作台直观展示 Agent 路径、OCR 结果、风险信息和审批入口；
- 通过 JWT、RBAC、请求幂等和 Redis 分布式锁，避免越权和重复审批；
- 使用 Docker Compose 一键部署，并用 Locust 验证核心 API 的并发能力。

本 MVP 的“退款”仅指**生成并持久化退款决策结果**，不调用真实支付、订单或资金系统。

### 1.2 MVP 已锁定范围

| 能力 | MVP 内容 |
| --- | --- |
| 用户与权限 | 客服、主管两种角色；用户名密码登录；JWT 鉴权；主管独占审批权限 |
| 工单 | 创建、本人/全量查询、详情查看、真实图片凭证上传 |
| 图片 | 仅 JPG/JPEG/PNG；单文件不超过 10MB；每单最多 3 张；不支持 PDF |
| Agent | Intake、OCR、风控、舆情、金额决策、HumanReview 人工节点 |
| OCR | 本地 PaddleOCR 推理，输出文字和置信度 |
| LLM | 通过可替换的 OpenAI 兼容客户端调用云端 LLM，分析工单材料，不抓取外网舆情 |
| 流转 | `RUNNING → SUSPENDED → COMPLETED` 三态；挂起用 Redis Checkpointer 保存图上下文 |
| 决策 | 仅产生 `AUTO_REFUNDED`、`APPROVED`、`REJECTED` 或 `FAILED` 业务结果 |
| 实时性 | 工单详情 SSE 推送；连接失败时每 2 秒轮询 |
| 部署与压测 | Docker Compose；Locust 压测核心 API |

### 1.3 明确不在 MVP 范围内的内容

- 真实支付退款、账务、资金冻结、对账、支付回调与补偿；
- 外网爬虫、第三方舆情抓取、社媒检索和数据采购；
- PDF/视频/音频等复杂凭证处理；
- 组织、团队、队列分配和复杂数据权限；
- JWT Refresh Token、令牌黑名单、单点登录；
- 自动超时拒绝、邮件/短信提醒；
- 复杂的多级审批、退回补料和人工工单派单；
- Prometheus/Grafana 的完整监控大盘（可预留接口和指标）。

---

## 2. 关键决策与设计原则

### 2.1 已确认的产品与技术决策

| 决策项 | 已确认结论 | 原因 |
| --- | --- | --- |
| 总体架构 | FastAPI + Redis Streams + Worker + LangGraph Checkpointer | 将 OCR/LLM 长耗时任务与 API 解耦，支持服务重启与挂起恢复 |
| 数据库 | PostgreSQL | 适合工单、审批、审计轨迹等关系型业务数据 |
| OCR 策略 | 本地 PaddleOCR | 满足本地模型部署与真实 OCR 演示要求 |
| LLM 策略 | 云端、OpenAI 兼容 LLM | 降低本地 GPU/模型运维成本，并保持提供方可替换 |
| 舆情来源 | 仅工单材料 | 避免外网数据合法性、稳定性和成本问题 |
| 退款动作 | 仅记录结果 | MVP 不产生真实资金风险 |
| 数据权限 | 客服仅看本人；主管看全部并审批 | 满足最小权限原则 |
| 审批超时 | 不自动终止 | 防止遗失需人工处理的工单，降低定时任务复杂度 |
| 状态失败表达 | `COMPLETED + FAILED + error_code` | 遵守题目要求的三态，同时保留失败语义 |
| 实时推送 | SSE + 轮询降级 | 单向状态推送足够，较 WebSocket 更轻量 |
| JWT | 仅 Access Token，有效期 2 小时 | MVP 控制复杂度，到期重新登录 |
| 压测口径 | 核心 API QPS≥200、P95<300ms、错误率<0.1% | Worker 异步处理外部 LLM，避免模型时延污染 API 指标 |

### 2.2 关键设计原则

1. **API 短请求、Worker 长任务**：建单和审批接口只做校验、落库、投递消息，不能同步等待 OCR 或 LLM。
2. **业务事实与图内部状态分离**：PostgreSQL 保存可查询的业务结果和审计轨迹；Redis Checkpointer 只保存 LangGraph 可恢复上下文。
3. **先保守、后自动**：OCR 低置信度、LLM 超时、模型格式不合法等不确定情况一律不自动通过。
4. **决策规则可测试**：金额、风险、舆情的最终路由下沉为无 I/O 的纯函数，Agent 仅负责采集和归一化信息。
5. **幂等与互斥缺一不可**：创建防重使用幂等键；审批冲突使用单工单分布式锁；数据库状态更新再做条件约束。
6. **审计可回放**：关键节点、模型结果、审批人、审批意见和错误码须可查询，供大屏和问题排查复用。

---

## 3. 总体技术架构

```text
┌────────────────────────────────────────────────────────────────────┐
│ React + TypeScript Dashboard                                        │
│ 登录 / 工单创建 / 图片上传 / Agent 流转图 / OCR 与风险结果 / 审批   │
└───────────────────────────────┬────────────────────────────────────┘
                                │ HTTPS：JWT、X-Idempotency-Key、SSE
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│ FastAPI API                                                         │
│ Auth + RBAC / 工单与文件 API / 幂等 / 审批锁 / SSE 事件读取         │
└───────────────┬─────────────────────┬──────────────────────────────┘
                │ SQL                 │ XADD
                ▼                     ▼
┌─────────────────────────┐  ┌──────────────────────────────────────┐
│ PostgreSQL               │  │ Redis                                │
│ users                    │  │ Streams：待执行/恢复任务队列         │
│ tickets                  │  │ Key：幂等记录、审批锁                 │
│ approvals                │  │ Checkpointer：LangGraph 挂起上下文    │
│ agent_traces             │  └─────────────────┬────────────────────┘
└─────────────────────────┘                    │ XREADGROUP
                                                 ▼
                                  ┌──────────────────────────────────┐
                                  │ Worker（可横向扩容）              │
                                  │ LangGraph 决策图                  │
                                  │ Intake → OCR → 风控 → 舆情 → 决策 │
                                  │        ↘ HumanReview interrupt   │
                                  └───────────┬───────────┬──────────┘
                                              │           │
                                       本地 OCR           云端 LLM
                                     PaddleOCR       OpenAI 兼容接口
```

### 3.1 进程职责

| 进程/服务 | 职责 | 不应承担的职责 |
| --- | --- | --- |
| 前端 | 表单校验、上传、展示与审批交互 | 决策规则、权限可信判断、锁控制 |
| FastAPI | 鉴权、权限、输入校验、文件接收、数据库事务、任务投递、事件读取 | 同步 OCR、同步 LLM、直接长时间运行图 |
| Redis | Stream 队列、幂等键、分布式锁、LangGraph checkpoint | 长期业务审计唯一存储 |
| Worker | 消费消息、调用 OCR/LLM、推进/恢复图、写轨迹和最终结果 | 直接对外暴露 HTTP API |
| PostgreSQL | 工单业务事实、审批审计、轨迹、错误码 | 保存可序列化图的唯一恢复状态 |

---

## 4. 核心业务流与状态机

### 4.1 决策规则

```text
IF amount > 300
   OR ocr_confidence < 0.60
   OR fraud_score >= 50
   OR sentiment != "LOW"
THEN HUMAN_REVIEW → SUSPENDED
ELSE AUTO_REFUND → COMPLETED + AUTO_REFUNDED
```

说明：

- `fraud_score` 为 0–100 的整数，数值越高表示越可疑；
- `sentiment` 是由工单材料风险分析得到的 `LOW`、`MEDIUM`、`HIGH`；这里的命名沿用需求中的“舆情风险”，不代表外网舆情监测；
- MVP 没有自动拒绝条件，最终拒绝由主管在人工审批中作出；
- 任一模型超时、模型输出解析失败或 OCR 不可信，优先进入人工审批而非自动通过。

### 4.2 LangGraph 路径

```text
START
  → Intake
  → OCR
  → FraudRisk
  → SentimentRisk
  → AmountDecision
       ├─ AUTO_REFUND → 完成（AUTO_REFUNDED） → END
       └─ HUMAN_REVIEW → interrupt() → Redis Checkpoint
                                         ↓
                              主管 APPROVE / REJECT
                                         ↓
                         Command(resume=...) → 完成 → END
```

### 4.3 三态与业务结果

| 流程状态 | 含义 | 可出现的业务结果 |
| --- | --- | --- |
| `RUNNING` | 已入队或 Worker 正在执行 Agent 图 | `PENDING` |
| `SUSPENDED` | 图在 HumanReview 节点中断，checkpoint 已保存 | `PENDING` |
| `COMPLETED` | 图已结束或处理不能继续 | `AUTO_REFUNDED`、`APPROVED`、`REJECTED`、`FAILED` |

### 4.4 场景一：金额超限挂起后审批

1. 客服提交金额 `350.00` 和凭证图片，API 校验 JWT、幂等键、图片格式和大小。
2. API 创建 `RUNNING` 工单，写入 Redis Stream，立即返回 `202 Accepted`（或业务约定的成功响应）。
3. Worker 依次执行 Intake、OCR、风控、舆情和金额决策，写入 Agent 轨迹。
4. 金额超过 300 元，决策为 `HUMAN_REVIEW`；HumanReview 调用 `interrupt()`。
5. Checkpointer 把线程状态保存到 Redis，工单更新为 `SUSPENDED`。
6. 主管提交 `APPROVE` 和审批意见；API 取得审批锁、校验状态，写审批记录和恢复任务。
7. Worker 消费恢复消息，用相同 `thread_id` 调用 `Command(resume={action: APPROVE})`。
8. 图完成，工单更新为 `COMPLETED + APPROVED`。

### 4.5 场景二：低金额、低风险自动完成

1. 客服提交金额 `128.00` 和清晰凭证。
2. OCR 置信度不低于 `0.60`，风险分为 `20`，舆情等级为 `LOW`。
3. 决策节点输出 `AUTO_REFUND`，无需进入 HumanReview。
4. Worker 写入 `COMPLETED + AUTO_REFUNDED`，大屏展示全部节点成功。

---

## 5. 模块、类与接口设计

### 5.1 推荐目录结构

```text
backend/
├── app/
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── security.py
│   ├── deps.py
│   ├── redis_client.py
│   ├── idempotency.py
│   ├── locks.py
│   ├── storage.py
│   ├── agents/
│   │   ├── state.py
│   │   ├── decision_rules.py
│   │   ├── ocr.py
│   │   ├── llm.py
│   │   ├── nodes.py
│   │   └── graph.py
│   ├── services/
│   │   ├── ticket_service.py
│   │   ├── approval_service.py
│   │   ├── trace_service.py
│   │   └── event_service.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── tickets.py
│   │   └── files.py
│   └── worker/
│       └── consumer.py
frontend/
├── src/pages/Login.tsx
├── src/pages/Dashboard.tsx
├── src/pages/TicketDetail.tsx
├── src/components/FlowCanvas.tsx
├── src/components/ApprovePanel.tsx
└── src/api/client.ts
```

### 5.2 后端核心类/接口职责

| 类/模块 | 主要职责 | 对外契约/关键方法 |
| --- | --- | --- |
| `Settings` | 集中读取数据库、Redis、JWT、模型、阈值、文件限制等环境配置 | `settings.AUTO_REFUND_MAX_AMOUNT` 等 |
| `User` / `Ticket` / `Approval` / `AgentTrace` | ORM 业务实体 | SQLAlchemy 模型 |
| `security.py` | 密码哈希、JWT 生成和验签 | `hash_password`、`verify_password`、`create_access_token`、`decode_token` |
| `deps.py` | FastAPI 依赖注入和 RBAC | `get_current_user`、`require_role(Role.SUPERVISOR)` |
| `FileStorage` | 受控文件命名、保存、读取路径生成和格式校验 | `save_upload(files) -> list[StoredFile]` |
| `IdempotencyService` | 提交幂等处理 | `claim_or_get(user_id, key, ticket_no)` |
| `ApprovalLock` | 同一工单审批互斥 | `acquire(ticket_id) -> LockToken`、`release(token)` |
| `decision_rules.py` | 无 I/O 的最终路由规则，是规则测试的唯一来源 | `decide(amount, ocr_confidence, fraud_score, sentiment) -> DecisionRoute` |
| `OcrClient` | 封装 PaddleOCR 初始化、单图识别和结果归一化 | `extract(image_path) -> OcrResult` |
| `LlmRiskClient` | 封装云端 LLM、超时、重试和结构化输出校验 | `score_fraud(material) -> int`、`classify_sentiment(material) -> RiskLevel` |
| `GraphState` | LangGraph 节点间的最小共享状态 | `ticket_id`、`thread_id`、`amount`、`ocr_*`、`fraud_score`、`sentiment`、`decision` |
| `nodes.py` | 执行具体 Agent；写状态增量，不处理持久化细节 | `intake_node`、`ocr_node`、`fraud_node`、`sentiment_node`、`decision_node`、`human_review_node` |
| `build_graph()` | 只定义节点及条件边 | `CompiledStateGraph` |
| `TicketService` | 建单、查询、数据权限过滤、任务投递 | `create_ticket()`、`get_ticket_for_user()`、`list_tickets_for_user()` |
| `ApprovalService` | 主管审批、状态校验、锁与恢复任务投递 | `submit_approval()` |
| `TraceService` | 节点开始/成功/失败/挂起轨迹落库 | `record_started()`、`record_finished()` |
| `StreamConsumer` | 消费初始/恢复消息并驱动图执行 | `process_initial()`、`process_resume()` |

### 5.3 Agent 接口与输出约束

| Agent | 输入 | 输出 | 失败处理 |
| --- | --- | --- | --- |
| Intake | 工单金额、图片清单、申请人 | 规范化基本字段 | 字段缺失：工单 `COMPLETED + FAILED` |
| OCR | 受控本地图片路径 | `ocr_text`、`ocr_confidence` | 图片损坏/无法识别：置信度 `0`，进入人工审批 |
| 风控 | 金额、OCR 文本、工单描述 | `fraud_score: 0..100` | 超时或解析失败：风险分设为保守值，进入人工审批 |
| 舆情 | 工单描述、OCR 文本 | `LOW/MEDIUM/HIGH` | 超时或非法输出：按 `HIGH` 保守处理，进入人工审批 |
| 金额决策 | 金额、OCR 置信度、欺诈分、舆情等级 | `AUTO_REFUND/HUMAN_REVIEW` | 不存在外部失败；规则函数必须可单测 |
| HumanReview | `ticket_id`、提示信息 | `APPROVE/REJECT` | 等待主管；不自动超时 |

---

## 6. 数据模型与表结构

> 以下为从“无既有业务库”开始的推荐表结构。生产实施使用 Alembic 管理迁移，避免运行时自动建表。

### 6.1 枚举

```text
user_role       = CUSTOMER_SERVICE | SUPERVISOR
ticket_status   = RUNNING | SUSPENDED | COMPLETED
ticket_outcome  = PENDING | AUTO_REFUNDED | APPROVED | REJECTED | FAILED
trace_status    = RUNNING | SUCCESS | SUSPENDED | FAILED
approval_action = APPROVE | REJECT
```

### 6.2 `users`：用户表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `username` | VARCHAR(64) | 非空、唯一索引 |
| `password_hash` | VARCHAR(255) | 非空，只存 bcrypt/Argon2 哈希 |
| `role` | `user_role` | 非空 |
| `is_active` | BOOLEAN | 默认 `true` |
| `created_at` | TIMESTAMPTZ | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 更新时间 |

### 6.3 `tickets`：工单主表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `ticket_no` | VARCHAR(64) | 非空、唯一、外部展示编号 |
| `creator_id` | FK → `users.id` | 非空，客服数据隔离依据 |
| `amount` | NUMERIC(12,2) | 非空，必须大于 0 |
| `complaint_text` | TEXT | 可空，工单描述 |
| `status` | `ticket_status` | 非空，默认 `RUNNING` |
| `outcome` | `ticket_outcome` | 非空，默认 `PENDING` |
| `thread_id` | VARCHAR(128) | 非空、唯一索引，LangGraph 恢复定位键 |
| `idempotency_key` | VARCHAR(128) | 非空；与 `creator_id` 联合唯一 |
| `ocr_text` | TEXT | OCR 聚合文本 |
| `ocr_confidence` | NUMERIC(5,4) | `0.0000–1.0000` |
| `fraud_score` | SMALLINT | `0–100` |
| `sentiment` | VARCHAR(16) | `LOW/MEDIUM/HIGH` |
| `error_code` | VARCHAR(64) | 仅 `FAILED` 时填写 |
| `error_message` | TEXT | 面向排障，避免保存敏感密钥 |
| `created_at` | TIMESTAMPTZ | 创建时间 |
| `updated_at` | TIMESTAMPTZ | 更新时间 |
| `completed_at` | TIMESTAMPTZ | 完成时间，可空 |

索引建议：

- `UNIQUE (creator_id, idempotency_key)`：数据库兜底防重；
- `INDEX (creator_id, created_at DESC)`：客服本人列表；
- `INDEX (status, created_at DESC)`：主管待审批列表；
- `UNIQUE (thread_id)`：恢复图时唯一定位。

### 6.4 `ticket_files`：凭证文件表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `ticket_id` | FK → `tickets.id` | 非空、级联删除 |
| `storage_key` | VARCHAR(512) | 非空，服务器内部路径或对象存储 Key，不暴露绝对路径 |
| `original_filename` | VARCHAR(255) | 展示用，需清理危险字符 |
| `content_type` | VARCHAR(100) | 仅允许 `image/jpeg`、`image/png` |
| `size_bytes` | BIGINT | 必须 ≤ 10MB |
| `sha256` | CHAR(64) | 文件完整性与排错用途 |
| `created_at` | TIMESTAMPTZ | 创建时间 |

### 6.5 `approvals`：审批审计表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `ticket_id` | FK → `tickets.id` | 非空 |
| `reviewer_id` | FK → `users.id` | 非空，必须为主管 |
| `action` | `approval_action` | 非空 |
| `comment` | TEXT | 可空，长度限制，例如 1000 字符 |
| `created_at` | TIMESTAMPTZ | 创建时间 |

在成功审批路径上，每个工单只允许一条有效审批。使用应用锁 + 条件更新保证，必要时增加 `UNIQUE(ticket_id)` 兜底。

### 6.6 `agent_traces`：Agent 执行轨迹表

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `ticket_id` | FK → `tickets.id` | 非空 |
| `sequence_no` | SMALLINT | 非空，节点执行序号 |
| `agent_name` | VARCHAR(64) | Intake/OCR/Fraud/Sentiment/Decision/HumanReview |
| `status` | `trace_status` | 非空 |
| `input_summary` | JSONB / TEXT | 脱敏后的输入摘要 |
| `output_summary` | JSONB / TEXT | OCR 结果、分数、路由结果等摘要 |
| `error_code` | VARCHAR(64) | 可空 |
| `started_at` | TIMESTAMPTZ | 非空 |
| `ended_at` | TIMESTAMPTZ | 可空 |

索引：`INDEX(ticket_id, sequence_no)`，供工单详情和大屏顺序渲染。

---

## 7. Redis、消息与一致性设计

### 7.1 Redis Key 设计

| Key 模式 | 示例 | 用途 | TTL |
| --- | --- | --- | --- |
| `idem:ticket:{creator_id}:{key}` | `idem:ticket:u100:k-uuid` | 建单幂等记录，值为 `ticket_id` | 24 小时 |
| `lock:approval:{ticket_id}` | `lock:approval:t100` | 同一工单审批互斥锁 | 10 秒，实际实现带唯一 token |
| `stream:ticket-jobs` | — | 初始执行与审批恢复消息队列 | Redis Stream 按运维策略保留 |
| `checkpoint:*` | LangGraph 管理 | 挂起图的状态与历史 | 与挂起工单保留策略一致，不设短业务 TTL |
| `event:ticket:{ticket_id}` | 可选 | SSE 轻量通知通道 | 短 TTL 或 Pub/Sub，不作为审计依据 |

### 7.2 幂等设计

**创建工单**：

1. 前端在一次用户点击生命周期中生成 UUID，置于 `X-Idempotency-Key`；重试必须复用同一 key。
2. API 验证 key 格式和长度后，以 `creator_id + key` 组成 Redis key，执行 `SET value NX EX 86400`。
3. 首次抢到 key 后创建数据库工单；若数据库事务失败，需删除/标记该 Redis key，避免“键已占用但工单不存在”。
4. 重复请求直接返回首次工单 ID 和当前状态。
5. PostgreSQL 的联合唯一索引提供 Redis 异常场景下的最终兜底。

**审批工单**：

1. 主管请求以 `SET lock:approval:{ticket_id} {random_token} NX PX 10000` 取锁。
2. 必须采用“比较 token 后删除”的 Lua 脚本释放锁，禁止无条件 `DEL`，避免锁过期后误删他人的新锁。
3. 数据库以条件更新约束状态：`WHERE id=? AND status='SUSPENDED' AND outcome='PENDING'`。
4. 更新成功后写审批记录、投递恢复 Stream 消息；再次审批返回 `409 Conflict`。

### 7.3 Redis Streams 消息格式

**新建工单消息**：

```json
{
  "type": "START",
  "ticket_id": "t_123",
  "thread_id": "lg_t_123",
  "created_at": "2026-08-17T10:00:00Z"
}
```

**审批恢复消息**：

```json
{
  "type": "RESUME",
  "ticket_id": "t_123",
  "thread_id": "lg_t_123",
  "approval_action": "APPROVE",
  "approval_id": "a_456"
}
```

Worker 应使用消费组：

- 成功完整处理后才 `XACK`；
- 处理异常不应直接确认；保留 Pending Entry 供重试/回收；
- 对不可恢复错误，更新为 `COMPLETED + FAILED`，记录 `error_code` 后再确认消息；
- 开发/演示环境可用单 Worker，压测或生产拓展时可增加消费者。

### 7.4 LangGraph 恢复约束

- 每个工单生成并持久化唯一 `thread_id`；
- 初始执行和恢复执行必须使用**同一 Redis Checkpointer 和同一 `thread_id`**；
- HumanReview 通过 `interrupt()` 产生中断，不手工 `pickle` 图对象；
- API 不能直接调用 `graph.resume()`，而应写入 `RESUME` 消息，由 Worker 串行恢复，以避免 API 与 Worker 争抢图状态；
- 如果 checkpoint 缺失，则将工单置为 `COMPLETED + FAILED`，错误码为 `CHECKPOINT_NOT_FOUND`，并保留审计记录。

---

## 8. API 契约与权限控制

### 8.1 认证与角色

JWT Payload：

```json
{
  "sub": "user_id",
  "role": "CUSTOMER_SERVICE | SUPERVISOR",
  "exp": "2 小时后的 Unix 时间戳"
}
```

| 角色 | 权限 |
| --- | --- |
| 客服（`CUSTOMER_SERVICE`） | 登录、创建工单、上传文件、查看本人列表和本人详情、查看本人事件流 |
| 主管（`SUPERVISOR`） | 拥有客服基础能力；查看全部工单；审批 `SUSPENDED` 工单 |

所有工单查询必须在服务层进行数据范围过滤，不能仅在前端隐藏按钮。

### 8.2 推荐接口清单

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | 公开 | 用户名密码登录，返回 Access Token |
| `POST` | `/api/tickets` | 客服/主管 | 创建工单；Header 必须携带 `X-Idempotency-Key` |
| `POST` | `/api/tickets/{id}/files` | 工单创建人或主管 | multipart 上传图片；最多 3 张 |
| `GET` | `/api/tickets` | 客服/主管 | 客服返回本人，主管返回全部；支持状态筛选/分页 |
| `GET` | `/api/tickets/{id}` | 创建人或主管 | 工单详情、文件、OCR、风险、决策、轨迹 |
| `GET` | `/api/tickets/{id}/events` | 创建人或主管 | SSE 状态/轨迹事件流 |
| `POST` | `/api/tickets/{id}/approval` | 仅主管 | 提交 `APPROVE` 或 `REJECT`，触发恢复任务 |
| `GET` | `/healthz` | 公开/内网 | API 健康检查 |
| `GET` | `/readyz` | 公开/内网 | DB、Redis 依赖检查 |

### 8.3 关键请求与响应示例

#### 登录

```http
POST /api/auth/login
Content-Type: application/json

{"username":"supervisor_01","password":"***"}
```

```json
{"access_token":"eyJ...","token_type":"bearer","expires_in":7200}
```

#### 创建工单

```http
POST /api/tickets
Authorization: Bearer <token>
X-Idempotency-Key: 4c4c450c-8fc9-4cb7-8757-982859cbb396
Content-Type: application/json

{"amount":"350.00","complaint_text":"商品破损，申请退款"}
```

```json
{
  "ticket_id": "t_123",
  "ticket_no": "RF202608170001",
  "status": "RUNNING",
  "outcome": "PENDING"
}
```

重复调用相同幂等键应返回相同 `ticket_id`，而不是新建工单。

#### 上传凭证

```http
POST /api/tickets/t_123/files
Authorization: Bearer <token>
Content-Type: multipart/form-data

files=@invoice.jpg
```

```json
{
  "ticket_id":"t_123",
  "files":[{"id":"f_001","filename":"invoice.jpg","content_type":"image/jpeg","size_bytes":248102}]
}
```

#### 主管审批

```http
POST /api/tickets/t_123/approval
Authorization: Bearer <supervisor-token>
Content-Type: application/json

{"action":"APPROVE","comment":"情况属实，批准退款"}
```

```json
{
  "ticket_id":"t_123",
  "status":"RUNNING",
  "outcome":"PENDING",
  "message":"审批已记录，决策流正在恢复"
}
```

说明：审批接口返回“恢复已入队”，最终结果通过详情接口/SSE 获得，不承诺同步完成。

### 8.4 标准错误语义

| HTTP 状态 | 场景 | 示例错误码 |
| --- | --- | --- |
| `400` | 金额、文件格式、审批动作非法 | `VALIDATION_ERROR` |
| `401` | 未携带/无效/过期 JWT | `UNAUTHORIZED` |
| `403` | 客服审批、越权查看他人工单 | `FORBIDDEN` |
| `404` | 工单不存在或无查看权限时按安全策略隐藏 | `TICKET_NOT_FOUND` |
| `409` | 已完成工单再次审批、并发审批、状态不匹配 | `TICKET_STATE_CONFLICT` |
| `413` | 超过图片数量或体积上限 | `FILE_TOO_LARGE` |
| `415` | 非 JPG/JPEG/PNG | `UNSUPPORTED_MEDIA_TYPE` |
| `422` | 请求体字段不符合约束 | `VALIDATION_ERROR` |
| `503` | Redis/数据库不可用，无法安全入队 | `DEPENDENCY_UNAVAILABLE` |

---

## 9. 大屏展示与实时更新

### 9.1 页面最小组成

| 区域 | 内容 | 数据来源 |
| --- | --- | --- |
| 工单列表 | 工单号、金额、状态、最终结果、风险分、创建时间 | `GET /api/tickets` |
| 工单摘要 | 客诉描述、上传图片、当前状态、最终结果/错误信息 | `GET /api/tickets/{id}` |
| Agent 流转图 | Intake → OCR → 风控 → 舆情 → 决策 → HumanReview 的节点状态 | `agent_traces` |
| OCR 卡片 | 聚合文字、平均/最低置信度、低置信度提示 | `tickets.ocr_*` + OCR 轨迹 |
| 风险卡片 | 欺诈分、舆情等级、触发的人工审核原因 | `tickets.fraud_score`、`tickets.sentiment`、决策轨迹 |
| 人工审批面板 | 仅当工单为 `SUSPENDED` 且当前用户为主管时展示 | 工单状态 + JWT role |

### 9.2 实时更新机制

1. Worker 每完成一个节点或状态切换，先写 `agent_traces`/`tickets`，再发布轻量事件。
2. SSE 接口只推送事件提醒，例如：`trace_updated`、`ticket_status_changed`、`completed`。
3. 前端收到事件后调用详情接口获取完整、可信的最新数据；不以 SSE 内容作为最终业务事实。
4. SSE 连接断开后，前端每 2 秒轮询详情；工单进入 `COMPLETED` 后停止轮询。
5. 轨迹节点的展示状态统一为：`PENDING`（灰）、`RUNNING`（蓝）、`SUCCESS`（绿）、`SUSPENDED`（黄）、`FAILED`（红）；必须显示文本或图标，不能仅用颜色传达状态。

---

## 10. 异常、边界与安全策略

### 10.1 必须覆盖的业务边界

| 条件 | 系统处理 |
| --- | --- |
| 同一客服重复提交相同 `X-Idempotency-Key` | 返回首次工单，不创建第二条记录、不重复入队 |
| 两名主管同时审批同一挂起工单 | 首位取得锁并完成条件更新；另一位收到 `409` |
| 非主管调用审批接口 | `403 FORBIDDEN` |
| 客服请求非本人详情 | `403` 或按接口安全策略返回 `404` |
| 上传超过 3 张或任意图片 >10MB | 拒绝请求，不保存文件 |
| 文件 MIME 或文件头不匹配图片格式 | 拒绝请求；不可仅信任浏览器传来的 Content-Type |
| OCR 无结果或置信度 <0.60 | 记录 OCR 结果，强制人工审核 |
| 云端 LLM 超时、5xx、限流 | 有限重试（建议 1 次、指数退避）；仍失败则按保守值进入人工审批 |
| LLM 非法 JSON/非法等级 | 结构化解析失败后有限重试；仍失败进入人工审批 |
| Redis Stream 消息重复投递 | Worker 以工单状态和 thread_id 判断，不重复推进已完成工单 |
| checkpoint 缺失 | `COMPLETED + FAILED`，记录 `CHECKPOINT_NOT_FOUND` |
| Worker 执行不可恢复异常 | 写 `FAILED` 结果和错误码；消息在完成状态落库后确认 |
| 审批已成功但恢复消息投递失败 | 记录待投递事件/失败日志并重试；实现时建议采用 outbox 模式，至少保证可人工补偿 |

### 10.2 安全最小要求

- 密码采用 bcrypt 或 Argon2 哈希，禁止明文、可逆加密或日志输出；
- `JWT_SECRET`、数据库密码和 LLM Key 仅通过环境变量/Secret 注入，禁止提交仓库；
- 开发环境默认账号与密码仅用于演示，生产部署须通过初始化脚本或管理员创建；
- 文件名须服务端重新命名；上传目录禁止执行权限；下载/预览需重新校验访问权限；
- LLM 提示词须明确“仅输出规定 JSON/枚举值”，并使用 Pydantic 校验模型输出；
- OCR 文本、用户输入不得拼接为系统指令；需标记为不可信材料；
- 审批意见和 OCR 文本按长度限制保存，避免日志/大屏被超长内容拖垮；
- 审计日志中不得保存 Authorization Header、密码或 LLM API Key。

---

## 11. 部署、压测与验收

### 11.1 Docker Compose 服务编排

| 服务 | 容器职责 | 健康检查 |
| --- | --- | --- |
| `frontend` | Nginx 托管 React 构建产物，反向代理 `/api` | HTTP 首页返回 200 |
| `api` | FastAPI API | `/healthz`、`/readyz` |
| `worker` | Redis Streams 消费者与 LangGraph 执行器 | 进程存活 + Redis 连通性 |
| `postgres` | PostgreSQL 业务数据 | `pg_isready` |
| `redis` | Stream、锁、幂等、checkpoint | `redis-cli ping` |

持久化卷建议：

- `postgres_data`：数据库数据；
- `uploads_data`：MVP 本地凭证文件；
- Redis 需要开启 AOF 或按演示环境要求配置持久化，确保挂起 checkpoint 不因容器重启丢失。

`api` 和 `worker` 使用 `restart: unless-stopped` 或等效策略，并配置健康检查。按照任务工单要求，强杀 API 或 Worker 后，应在 5 秒内恢复进程服务能力；实际验收时记录测试证据。

### 11.2 Locust 压测口径

压测对象是**短时核心 API**，而不是云端 LLM 完整完成时长：

- 登录：`POST /api/auth/login`；
- 建单：`POST /api/tickets`；
- 工单列表：`GET /api/tickets`；
- 工单详情：`GET /api/tickets/{id}`；
- 审批入队：`POST /api/tickets/{id}/approval`（预置挂起工单）。

验收基线：

| 指标 | 标准 |
| --- | --- |
| QPS | ≥ 200 |
| P95 延迟 | < 300ms |
| 错误率 | < 0.1% |
| 稳定性 | API、Worker、PostgreSQL、Redis 无 OOM、死锁、反复重启 |

注意事项：

- LLM/OCR 任务由 Worker 异步执行，建单接口只确认“已受理”；因此不能把外部模型耗时混入核心 API P95；
- 为避免真实云端模型的限流和成本影响 API 性能验证，压测环境可将 Worker 模型调用替换为固定延迟的 Stub，但须在报告中明确区分“API 性能”与“真实 AI 推理时延”；
- 压测必须使用独立数据集/幂等键，避免大量重复命中幂等缓存造成虚高；
- 报告应记录宿主机 CPU、内存、容器资源限制、并发用户数、加压速率、持续时间和原始 Locust 输出。

### 11.3 最小验收用例

| 编号 | 用例 | 预期结果 |
| --- | --- | --- |
| E2E-01 | 350 元 + 清晰图片 + 低风险 | 工单进入 `SUSPENDED`；主管审批后进入 `COMPLETED + APPROVED` |
| E2E-02 | 128 元 + OCR≥0.60 + 风险20 + LOW | 直接进入 `COMPLETED + AUTO_REFUNDED` |
| E2E-03 | OCR 置信度低 | 强制进入 `SUSPENDED` |
| E2E-04 | 相同幂等键并发/重复建单 | 返回相同工单，数据库仅一条 |
| E2E-05 | 两主管并发审批 | 仅一条审批有效；另一条得到 `409` |
| E2E-06 | 客服审批/越权读单 | 返回 `403` 或安全的 `404` |
| E2E-07 | LLM 超时/格式错误 | 不自动通过，保守进入人工审批 |
| E2E-08 | Worker/API 容器强杀 | 5 秒内按容器策略恢复；未完成消息可继续处理或被标记失败 |

---

## 12. 待实施前确认项

本轮需求澄清已解决大部分影响 MVP 结构的模糊项。以下内容不阻塞文档定稿，但在编码/部署前必须给出具体值或由配置默认值承接：

| 编号 | 项目 | 推荐默认/待确认内容 | 影响 |
| --- | --- | --- | --- |
| 1 | 云端 LLM 提供方与模型名 | 采用可替换 OpenAI 兼容接口；具体供应商、模型、API Key 由部署环境决定 | `LlmRiskClient` 配置与成本 |
| 2 | 演示用户初始化 | 至少创建 1 个客服与 1 个主管；密码不得硬编码进生产镜像 | 登录、Locust 用例 |
| 3 | 本地文件保留周期 | MVP 可与 Docker Volume 生命周期一致；后续建议定期清理/迁移对象存储 | 磁盘占用与隐私 |
| 4 | 失败工单补偿入口 | MVP 可仅展示失败原因；后续是否提供“重新处理”按钮 | 失败恢复体验 |
| 5 | LLM 调用成本控制 | 建议设置超时、最大重试 1 次、并发上限与请求长度上限 | 成本、限流、Worker 吞吐 |
| 6 | 数据合规要求 | 如用于真实用户数据，需确认数据脱敏、留存期限、云端 LLM 数据出境/授权策略 | 上线合规 |

---

## 结论

本方案以**异步解耦、可恢复状态机、保守自动化和可审计决策**为核心，满足原始需求中的用户鉴权、多 Agent 协作、三态流转、Redis 挂起恢复、请求防重、大屏展示、Docker Compose 与 Locust 压测要求。

对于 MVP，最关键的实现红线是：

1. 不能在 API 请求中同步执行 OCR 或 LLM；
2. 不能把 Redis 当作工单业务事实的唯一来源；
3. 不能用无 token 的 `DEL` 释放分布式锁；
4. 不能让异常或模型不确定性触发自动通过；
5. 不能绕过 Worker 由 API 直接恢复 LangGraph；
6. 不能将“记录退款决策”误实现为“调用真实支付退款”。
