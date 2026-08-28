# Tasks: 多 Agent 协同客诉舆情退赔决策系统（MVP）

**Input**: Design documents from `/specs/001-refund-decision-mvp/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/

**Tests**: 本项目的宪法（`.specify/memory/constitution.md`）强制要求「核心决策路由有单元测试、关键并发/幂等/审批路径有集成测试、提交前通过 E2E-01~08」，故在对应故事阶段包含测试任务。

**Organization**: 任务按用户故事分组，支持独立实现与独立验证。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1~US6）
- 描述含精确文件路径

## Path Conventions

- 后端：`backend/app/...`、`backend/tests/...`
- 前端：`frontend/src/...`
- 根目录：`docker-compose.yml`、`.env.example`、`locustfile.py`、`README.md`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 项目初始化与基础结构

- [X] T001 在仓库根目录创建 `backend/` 与 `frontend/` 目录结构，按 plan.md「Project Structure」布局
- [X] T002 初始化后端 Python 项目：创建 `backend/pyproject.toml`，声明依赖 FastAPI、LangGraph、`langgraph-checkpoint-redis`、Transformers、SQLAlchemy、PyJWT、redis-py、openai、pytest
- [X] T003 [P] 初始化前端：创建 `frontend/`（React + TypeScript + Vite + ECharts），含 `frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`
- [X] T004 [P] 创建 `docker-compose.yml`（服务：frontend/api/worker/postgres/redis，含健康检查与持久化卷）与 `.env.example`（`JWT_SECRET`、`DATABASE_URL`、`REDIS_URL`、`LLM_API_KEY` 等占位）
- [X] T005 实现 `backend/app/config.py`：`Settings` 集中读取 DB/Redis/JWT/模型/阈值/文件限制配置（含 `AUTO_REFUND_MAX_AMOUNT`、`OCR_CONFIDENCE_THRESHOLD` 等）
- [X] T006 初始化 Alembic：创建 `backend/alembic/`、`backend/alembic.ini`、`backend/alembic/env.py`，接入 `config.py` 的 `DATABASE_URL`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 所有用户故事都必须依赖的核心基础设施

**⛔ CRITICAL**: 本阶段未完成前，任何用户故事都不能开始

- [X] T007 实现 `backend/app/db.py`：SQLAlchemy engine 与 session 管理（`get_db` 依赖）
- [X] T008 实现 `backend/app/models.py`：五实体 ORM（`User`/`Ticket`/`TicketFile`/`Approval`/`AgentTrace`）与枚举（`user_role`/`ticket_status`/`ticket_outcome`/`trace_status`/`approval_action`），字段与约束按 data-model.md
- [X] T009 生成初始迁移 `backend/alembic/versions/0001_initial.py`：建 5 张表 + 索引（`UNIQUE(creator_id,idempotency_key)`、`UNIQUE(thread_id)`、`INDEX(creator_id,created_at)`、`INDEX(status,created_at)`、`INDEX(ticket_id,sequence_no)`）
- [X] T010 [P] 实现 `backend/app/security.py`：`hash_password`、`verify_password`、`create_access_token`、`decode_token`（bcrypt/Argon2 + PyJWT，2h 有效期）
- [X] T011 [P] 实现 `backend/app/deps.py`：`get_current_user`、`require_role(Role.SUPERVISOR)` 依赖注入与 RBAC
- [X] T012 [P] 实现 `backend/app/redis_client.py`：Redis 连接与客户端封装
- [X] T013 [P] 实现 `backend/app/schemas.py`：Pydantic 请求/响应模型（登录、建单、上传、审批、工单详情）
- [X] T014 实现 `backend/app/main.py`：FastAPI 应用装配、`/healthz`、`/readyz`、全局错误处理器（映射 contracts/api.md 标准错误语义）
- [X] T015 实现 `backend/app/routers/auth.py`：`POST /api/auth/login`，返回 Access Token

**Checkpoint**: 基础就绪 —— 用户故事可开始并行实现

---

## Phase 3: User Story 1 - 客服登录并提交退赔工单 (Priority: P1) 🎯 MVP

**Goal**: 客服登录后提交工单（金额/描述/凭证图片），系统受理并返回工单编号，客服可查看本人列表与详情

**Independent Test**: 客服登录 → 提交工单（含图片）→ 收到工单编号 → 列表与详情可见（工单处于待处理状态即可）

### Implementation for User Story 1

- [X] T016 [P] [US1] 实现 `backend/app/storage.py`：`FileStorage.save_upload(files)`，受控命名、格式校验（JPG/JPEG/PNG、≤10MB、每单≤3）、`sha256` 计算与保存
- [X] T017 [P] [US1] 实现 `backend/app/idempotency.py`：`IdempotencyService.claim_or_get(user_id, key, ticket_no)`，Redis `SET NX EX` 基础幂等
- [X] T018 [US1] 实现 `backend/app/services/ticket_service.py`：`create_ticket()`（校验+落库+幂等）、`get_ticket_for_user()`、`list_tickets_for_user()`（数据权限过滤，客服仅本人）
- [X] T019 [US1] 实现 `backend/app/routers/tickets.py`：`POST /api/tickets`（要求 `X-Idempotency-Key`）、`GET /api/tickets`（状态筛选/分页）、`GET /api/tickets/{id}`
- [X] T020 [US1] 实现 `backend/app/routers/files.py`：`POST /api/tickets/{id}/files`（multipart 上传，权限校验）
- [X] T021 [US1] 集成测试 `backend/tests/integration/test_tickets.py`：建单成功/金额非法/文件超限/客服越权看他人单返回 403 或 404

**Checkpoint**: 用户故事 1 可独立运行、独立验证

---

## Phase 4: User Story 2 - 低风险工单自动退赔决策 (Priority: P1)

**Goal**: 工单提交后自动执行「凭证识别 → 风险 → 舆情 → 金额决策」链路，低风险工单无需人工自动给出退赔结论

**Independent Test**: 提交小金额 + 清晰凭证 + 低风险工单，系统在无人工干预下自动产生「自动退赔」结果

### Tests for User Story 2

- [X] T022 [P] [US2] 单元测试 `backend/tests/unit/test_decision_rules.py`：覆盖 `decide()` 全部阈值边界（金额=300、置信度=0.60、欺诈=50、舆情非 LOW）

### Implementation for User Story 2

- [X] T023 [P] [US2] 实现 `backend/app/agents/state.py`：`GraphState`（`ticket_id`/`thread_id`/`amount`/`ocr_*`/`fraud_score`/`sentiment`/`decision`）
- [X] T024 [P] [US2] 实现 `backend/app/agents/decision_rules.py`：无 I/O 纯函数 `decide(amount, ocr_confidence, fraud_score, sentiment)`（决策唯一来源）
- [X] T025 [P] [US2] 实现 `backend/app/agents/ocr.py`：`OcrClient.extract(image_path)` 封装 Transformers/TrOCR 加载，输出文本与置信度（多图取最小置信度）
- [X] T026 [P] [US2] 实现 `backend/app/agents/llm.py`：`LlmRiskClient.score_fraud()` / `classify_sentiment()`，api_key + base_url 调用 OpenAI 兼容接口 + 结构化输出校验 + 失败兜底（重试→保守值→转人工）
- [X] T027 [US2] 实现 `backend/app/agents/nodes.py`：`intake_node`/`evidence_node`/`fraud_node`/`sentiment_node`/`decision_node`，只写状态增量、不落业务判断
- [X] T028 [US2] 实现 `backend/app/agents/graph.py`：`build_graph()` 定义节点与条件边，注入 Redis Checkpointer
- [X] T029 [US2] 实现 `backend/app/worker/consumer.py`：消费组 `XREADGROUP` 拉取、`process_initial()` 驱动图执行、成功才 `XACK`、异常保留 Pending
- [X] T030 [US2] 在 `backend/app/services/ticket_service.py` 中接线：`create_ticket()` 落库后 `XADD START` 消息到 `stream:tickets`
- [X] T031 [US2] 集成测试 `backend/tests/integration/test_auto_refund.py`：验证低风险工单自动流转至 `COMPLETED + AUTO_REFUNDED`（E2E-02）

**Checkpoint**: 用户故事 1 + 2 均可独立运行；自动退赔链路打通

---

## Phase 5: User Story 3 - 高风险/不确定工单转主管人工审批 (Priority: P1)

**Goal**: 高风险/不确定工单暂停自动流程、保留中间状态，主管审批后从断点恢复并得出最终结果

**Independent Test**: 提交金额 > 300 元工单 → 进入「待人工审批」→ 主管批准/拒绝 → 工单得到最终结果

### Implementation for User Story 3

- [X] T032 [P] [US3] 实现 `backend/app/locks.py`：`ApprovalLock.acquire(ticket_id)/release(token)`，`SET NX PX` + 比较 token 的 Lua 释放（禁止无条件 DEL）
- [X] T033 [US3] 在 `backend/app/agents/nodes.py` 实现 `human_review_node`：调用 `interrupt()` 挂起；在 `backend/app/agents/graph.py` 增加 `HUMAN_REVIEW` 分支与 `Command(resume=...)` 恢复边
- [X] T034 [US3] 实现 `backend/app/services/approval_service.py`：`submit_approval()`（取锁 + 状态条件更新 `WHERE status='SUSPENDED' AND outcome='PENDING'` + 写审批记录 + `XADD RESUME` + 释放锁）
- [X] T035 [US3] 在 `backend/app/routers/tickets.py` 增加 `POST /api/tickets/{id}/approval`（仅主管 RBAC），返回「恢复已入队」
- [X] T036 [US3] 在 `backend/app/worker/consumer.py` 增加 `process_resume()`：用同一 `thread_id` 调 `Command(resume=...)`；checkpoint 缺失时落 `COMPLETED + FAILED + CHECKPOINT_NOT_FOUND`
- [X] T037 [US3] 集成测试 `backend/tests/integration/test_approval.py`：金额超限挂起→主管批准/拒绝（E2E-01）、OCR 低置信度强制挂起（E2E-03）、客服审批返回 403

**Checkpoint**: 用户故事 3 可独立运行；人工兜底闭环打通

---

## Phase 6: User Story 4 - 大屏实时展示决策过程 (Priority: P2)

**Goal**: 大屏实时查看工单列表、决策执行路径、凭证识别文本、风险评分与审批入口

**Independent Test**: 提交工单后大屏实时出现该工单，随决策推进展示各环节状态，最终展示审批入口或最终结论

### Implementation for User Story 4

- [X] T038 [P] [US4] 实现 `backend/app/services/event_service.py`：节点/状态切换后发布轻量事件（`trace_updated`/`ticket_status_changed`/`completed`）
- [X] T039 [US4] 在 `backend/app/routers/tickets.py` 增加 `GET /api/tickets/{id}/events`（SSE 事件流）
- [X] T040 [US4] 在 `backend/app/agents/nodes.py` 与 `worker/consumer.py` 接线：写轨迹/状态后调用 `event_service` 发布事件
- [X] T041 [P] [US4] 实现 `frontend/src/api/client.ts`：API 客户端（登录/建单/上传/列表/详情/审批/SSE，携带 JWT 与幂等键）
- [X] T042 [P] [US4] 实现 `frontend/src/pages/Login.tsx`：登录页
- [X] T043 [P] [US4] 实现 `frontend/src/pages/Dashboard.tsx`：工单列表 + 摘要（状态筛选、分页、断线后 2s 轮询）
- [X] T044 [P] [US4] 实现 `frontend/src/components/FlowCanvas.tsx`：Agent 流转图（节点状态文本+颜色，不能仅用颜色传达状态）
- [X] T045 [P] [US4] 实现 `frontend/src/pages/TicketDetail.tsx`：工单详情 + OCR 卡片 + 风险卡片 + `frontend/src/components/ApprovePanel.tsx`（仅主管且 `SUSPENDED` 时展示）
- [ ] T046 [US4] 手动验证：通过大屏完成建单→观察流转→审批全流程（对应 quickstart.md）

**Checkpoint**: 大屏可实时展示决策过程

---

## Phase 7: User Story 5 - 防重复提交与并发审批互斥 (Priority: P2)

**Goal**: 重复/并发提交只产生一张工单；并发审批仅一笔生效，杜绝重复退赔与重复审批

**Independent Test**: 相同提交标识重复/并发建单仅一张；两名主管并发审批仅一条有效

### Tests for User Story 5

- [X] T047 [P] [US5] 集成测试 `backend/tests/integration/test_idempotency.py`：相同幂等键重复/并发建单仅一张（E2E-04）

### Implementation for User Story 5

- [X] T048 [US5] 加固 `backend/app/idempotency.py` 三层防线：Redis `SET NX` 首抢建单、DB 事务失败回滚 key、重复请求返回原工单 ID（DB 联合唯一索引兜底）
- [X] T049 [US5] 加固 `backend/app/services/approval_service.py`：DB 条件更新兜底（影响行数 0 → 409），审批已完成/状态不匹配返回 `TICKET_STATE_CONFLICT`
- [X] T050 [US5] 集成测试 `backend/tests/integration/test_concurrency.py`：两主管并发审批仅一条生效、另一条 409（E2E-05）

**Checkpoint**: 防重与互斥加固完成

---

## Phase 8: User Story 6 - 决策全程可审计 (Priority: P3)

**Goal**: 任一工单的决策过程（环节输入/输出、风险结果、审批人、审批意见、失败原因）可追溯

**Independent Test**: 任取已处理工单，可查询完整决策环节记录、审批人与意见、失败原因

### Implementation for User Story 6

- [X] T051 [P] [US6] 实现 `backend/app/services/trace_service.py`：`record_started()`/`record_finished()`，写入 `agent_traces`（脱敏输入/输出摘要、错误码）
- [X] T052 [US6] 在 `backend/app/agents/nodes.py` 与 `worker/consumer.py` 接线：各节点开始/成功/失败/挂起时记录轨迹（`sequence_no` 递增）
- [X] T053 [US6] 在 `backend/app/services/ticket_service.py` 详情返回中包含 `agent_traces`（按 `sequence_no` 排序）；确保不落 Authorization Header/密码/LLM Key
- [X] T054 [US6] 集成测试 `backend/tests/integration/test_trace.py`：失败工单可查询到 `error_code` 与轨迹，且不含敏感凭据

**Checkpoint**: 审计可回放

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: 跨故事完善与验收

- [X] T055 [P] 实现 `locustfile.py`：压测登录/建单/列表/详情/审批入队五个核心 API
- [X] T056 [P] 编写 `README.md`：一键启动命令、演示账号初始化、压测与验收说明（含 DeepSeek 接入与生产环境规范）
- [X] T057 安全加固复核：文件头校验（非仅信任 Content-Type）、提示词注入防护（OCR/用户输入标记为不可信）、文件名清理、审计脱敏
- [ ] T058 执行 `quickstart.md` 全量验证（E2E-01~E2E-08 + Locust 冒烟），记录验收证据

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: 无依赖，可立即开始
- **Foundational (Phase 2)**: 依赖 Setup 完成，**阻塞所有用户故事**
- **User Stories (Phase 3~8)**: 均依赖 Foundational 完成
- **Polish (Phase 9)**: 依赖目标用户故事完成

### User Story Dependencies

- **US1 (P1)**: Foundational 后即可开始；无其他故事依赖
- **US2 (P1)**: 依赖 US1（需工单存在）；低风险自动退赔链路
- **US3 (P1)**: 依赖 US1 + US2（复用图与节点，增加人工节点）；可与 US2 并行推进图定义
- **US4 (P2)**: 依赖 US2/US3（需轨迹与状态可展示）；SSE 与前端
- **US5 (P2)**: 加固 US1 的幂等与 US3 的锁；可与 US4 并行
- **US6 (P3)**: 依赖 US2/US3（轨迹由节点写出）；审计展示

### Within Each User Story

- 测试（如包含）先写并确保失败，再实现
- 模型 → 服务 → 端点 → 集成
- 核心实现 → 接线/集成 → 独立验证

### Parallel Opportunities

- Setup 阶段 [P] 任务可并行（T003/T004）
- Foundational 阶段 [P] 任务可并行（T010~T013）
- 每个用户故事内，不同文件的 [P] 任务可并行
- US4 与 US5 可在 US2/US3 完成后并行推进
- 前端任务 T041~T045 可在 API 契约冻结后并行

---

## Parallel Example: User Story 2

```bash
# 并行实现无依赖的 Agent 组件：
Task: "实现 backend/app/agents/state.py 的 GraphState"
Task: "实现 backend/app/agents/decision_rules.py 的 decide 纯函数"
Task: "实现 backend/app/agents/ocr.py 的 OcrClient"
Task: "实现 backend/app/agents/llm.py 的 LlmRiskClient"
# 随后（依赖上述）：
Task: "实现 backend/app/agents/nodes.py 各节点"
Task: "实现 backend/app/agents/graph.py build_graph"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1 Setup
2. 完成 Phase 2 Foundational（关键阻塞）
3. 完成 Phase 3 US1
4. **STOP 并验证**：US1 独立可测（登录→建单→上传→查看）
5. 可先部署/演示

### Incremental Delivery

1. Setup + Foundational → 基础就绪
2. US1 → 独立验证 → 部署/演示（MVP！）
3. US2 → 独立验证 → 自动退赔链路
4. US3 → 独立验证 → 人工兜底闭环
5. US4 + US5 → 大屏 + 防重/互斥
6. US6 → 审计可回放
7. 每步不破坏前序故事

### Parallel Team Strategy

多开发者时：

1. 团队共同完成 Setup + Foundational
2. Foundational 完成后：
   - 开发者 A：US1（建单/上传/查询）
   - 开发者 B：US2（Agent 图与 Worker）
   - 开发者 C：前端骨架 + US4 大屏
3. US3 在 US2 图定义就绪后跟进；US5/US6 作为加固与审计收尾

---

## Notes

- [P] 任务 = 不同文件、无依赖，可并行
- [Story] 标签将任务映射到用户故事，便于追踪
- 每个用户故事应可独立完成与验证
- 每个任务或逻辑组完成后提交
- 可在任一 Checkpoint 停下独立验证故事
- 避免：模糊任务、同文件冲突、破坏独立性的跨故事依赖
