# Data Model: 多 Agent 协同客诉舆情退赔决策系统（MVP）

> 上游基线：《需求与技术方案说明书.md》§9。生产实施用 Alembic 管理迁移，禁止运行时自动建表。

## 实体关系总览

```text
users 1 ──── n tickets 1 ──── n ticket_files
  │                │
  │                │ 1 ──── 0..1 approvals (成功路径每工单至多一条有效审批)
  │                │ 1 ──── n agent_traces
  │                │
  └(creator_id)    └(reviewer_id 必须为主管)
```

## 枚举

| 枚举 | 取值 |
| --- | --- |
| `user_role` | `CUSTOMER_SERVICE` \| `SUPERVISOR` |
| `ticket_status` | `RUNNING` \| `SUSPENDED` \| `COMPLETED` |
| `ticket_outcome` | `PENDING` \| `AUTO_REFUNDED` \| `APPROVED` \| `REJECTED` \| `FAILED` |
| `trace_status` | `RUNNING` \| `SUCCESS` \| `SUSPENDED` \| `FAILED` |
| `approval_action` | `APPROVE` \| `REJECT` |

## 实体定义

### users（用户）

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `username` | VARCHAR(64) | 非空、唯一索引 |
| `password_hash` | VARCHAR(255) | 非空，只存 bcrypt/Argon2 哈希 |
| `role` | `user_role` | 非空 |
| `is_active` | BOOLEAN | 默认 `true` |
| `created_at` / `updated_at` | TIMESTAMPTZ | 时间戳 |

### tickets（工单主表）

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `ticket_no` | VARCHAR(64) | 非空、唯一、外部展示编号 |
| `creator_id` | FK → users.id | 非空，客服数据隔离依据 |
| `amount` | NUMERIC(12,2) | 非空，必须大于 0 |
| `complaint_text` | TEXT | 可空 |
| `status` | `ticket_status` | 非空，默认 `RUNNING` |
| `outcome` | `ticket_outcome` | 非空，默认 `PENDING` |
| `thread_id` | VARCHAR(128) | 非空、唯一，LangGraph 恢复定位键 |
| `idempotency_key` | VARCHAR(128) | 非空；与 `creator_id` 联合唯一 |
| `ocr_text` | TEXT | OCR 聚合文本 |
| `ocr_confidence` | NUMERIC(5,4) | `0.0000–1.0000` |
| `fraud_score` | SMALLINT | `0–100` |
| `sentiment` | VARCHAR(16) | `LOW/MEDIUM/HIGH` |
| `error_code` | VARCHAR(64) | 仅 `FAILED` 时填写 |
| `error_message` | TEXT | 面向排障，避免保存敏感密钥 |
| `created_at` / `updated_at` / `completed_at` | TIMESTAMPTZ | `completed_at` 可空 |

索引：`UNIQUE(creator_id, idempotency_key)`；`INDEX(creator_id, created_at DESC)`；
`INDEX(status, created_at DESC)`；`UNIQUE(thread_id)`。

### ticket_files（凭证文件）

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `ticket_id` | FK → tickets.id | 非空、级联删除 |
| `storage_key` | VARCHAR(512) | 非空，内部路径，不暴露绝对路径 |
| `original_filename` | VARCHAR(255) | 展示用，需清理危险字符 |
| `content_type` | VARCHAR(100) | 仅 `image/jpeg`、`image/png` |
| `size_bytes` | BIGINT | ≤ 10MB |
| `sha256` | CHAR(64) | 完整性与排错 |
| `created_at` | TIMESTAMPTZ | 创建时间 |

### approvals（审批审计）

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `ticket_id` | FK → tickets.id | 非空 |
| `reviewer_id` | FK → users.id | 非空，必须为主管 |
| `action` | `approval_action` | 非空 |
| `comment` | TEXT | 可空，长度限制（如 1000 字符） |
| `created_at` | TIMESTAMPTZ | 创建时间 |

约束：成功审批路径每工单至多一条有效审批（应用锁 + 条件更新，必要时 `UNIQUE(ticket_id)` 兜底）。

### agent_traces（决策轨迹）

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID / BIGINT | 主键 |
| `ticket_id` | FK → tickets.id | 非空 |
| `sequence_no` | SMALLINT | 非空，节点执行序号 |
| `agent_name` | VARCHAR(64) | Intake/Evidence/Fraud/Sentiment/Decision/HumanReview |
| `status` | `trace_status` | 非空 |
| `input_summary` | JSONB / TEXT | 脱敏后的输入摘要 |
| `output_summary` | JSONB / TEXT | 结果摘要 |
| `error_code` | VARCHAR(64) | 可空 |
| `started_at` / `ended_at` | TIMESTAMPTZ | `ended_at` 可空 |

索引：`INDEX(ticket_id, sequence_no)`。

## 校验规则

| 规则 | 来源 |
| --- | --- |
| `amount` 必须 > 0 | FR-001/FR-002 |
| 图片仅 JPG/JPEG/PNG，单文件 ≤ 10MB，每单 ≤ 3 张 | FR-003 |
| `fraud_score ∈ [0,100]`，`sentiment ∈ {LOW,MEDIUM,HIGH}` | FR-005 |
| `ocr_confidence ∈ [0.0,1.0]` | FR-005 |
| 审批人必须为主管角色 | FR-007 |

## 状态机

### 工单流程状态与业务结果

| 流程状态 | 含义 | 可出现的业务结果 |
| --- | --- | --- |
| `RUNNING` | 已入队或 Worker 执行中 | `PENDING` |
| `SUSPENDED` | 图在人工审批节点中断，checkpoint 已保存 | `PENDING` |
| `COMPLETED` | 图结束或不能继续 | `AUTO_REFUNDED` / `APPROVED` / `REJECTED` / `FAILED` |

失败语义通过 `COMPLETED + FAILED + error_code` 表达，既遵守三态又保留失败原因。

### 决策路由（唯一来源：`decide` 纯函数）

```text
IF amount > 300 OR ocr_confidence < 0.60 OR fraud_score >= 50 OR sentiment != "LOW"
THEN HUMAN_REVIEW → SUSPENDED
ELSE AUTO_REFUND → COMPLETED + AUTO_REFUNDED
```

### Agent 执行路径

```text
START → Intake → Evidence(OCR) → Fraud → Sentiment → Decision
         ├─ AUTO_REFUND → END（AUTO_REFUNDED）
         └─ HUMAN_REVIEW → interrupt() → Redis Checkpoint
                             ↓ 主管 APPROVE / REJECT
                           Command(resume=...) → END（APPROVED / REJECTED）
```
