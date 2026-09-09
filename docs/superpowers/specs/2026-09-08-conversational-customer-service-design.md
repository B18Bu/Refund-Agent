# 对话式智能客服设计

## 目标

将现有单轮“商品咨询助手”升级为面向消费者的连续对话式智能客服。第一版覆盖商品咨询、本人订单查询、退款售后规则说明和人工承接。客服必须给出可核验依据，不能由模型直接执行退款、退单、订单变更或隐私设置变更。

## 不在范围内

- 不复用退款 `Ticket` 作为客服会话或人工客服工单。
- 不改变 JWT、现有角色、退款审批锁、Redis 幂等键或支付语义。
- 不让模型调用具有写入副作用的订单、退款或隐私接口。
- 不使用模型决定路由、重试或数据转换；意图路由使用确定性规则。

## 用户体验

`/shop/assistant` 改为聊天工作区：左侧列出当前用户的最近会话，右侧显示按时间排序的连续消息流。用户发送消息后可继续追问，服务端以会话历史和本轮检索结果生成回复。

每条助手回复包含：文本、类型、可公开的资料来源、关联订单的只读摘要，或受控业务入口。无依据、命中安全策略、涉及执行型请求或用户主动转人工时，展示“转人工”操作。转人工后显示客服会话工单状态，用户仍可阅读历史但不再由模型继续回复。

## 数据模型与迁移

新增显式 SQL 迁移，禁止依赖 `create_all`：

- `customer_support_conversations`：`id`、`user_id`、`status`（`OPEN`、`ESCALATED`、`CLOSED`）、`title`、`created_at`、`updated_at`。
- `customer_support_messages`：`id`、`conversation_id`、`sender`（`CUSTOMER`、`ASSISTANT`、`SYSTEM`）、`content_masked`、`intent`、`evidence` JSON、`created_at`。仅存储经 DLP 处理后的文本，不存原始 PII 或提示词材料。
- `customer_support_cases`：`id`、`conversation_id`（唯一）、`user_id`、`status`（`OPEN`、`IN_PROGRESS`、`RESOLVED`）、`trigger_reason`、`summary_masked`、`assigned_to`、时间戳。它是独立客服工单，不关联退款审批状态。

现有数据与 API 保持兼容：旧的 `POST /api/customer-assistant/reply` 在迁移期保留，但页面改用新会话 API。迁移通过单容器入口脚本在 Supervisor 启动前执行。

## 后端接口

消费者接口均要求 `Role.CUSTOMER`，并强制会话归属：

- `POST /api/customer-assistant/conversations`：创建会话。
- `GET /api/customer-assistant/conversations`：列出当前用户会话。
- `GET /api/customer-assistant/conversations/{id}`：读取当前用户会话与消息。
- `POST /api/customer-assistant/conversations/{id}/messages`：写入脱敏用户消息，执行确定性路由、只读检索和受约束回复。
- `POST /api/customer-assistant/conversations/{id}/escalations`：按安全、无证据、执行型请求或用户请求创建一次客服会话工单。采用数据库唯一约束与条件写入保证幂等。

客服和主管接口要求 `Role.CS` 或 `Role.SV`：

- `GET /api/customer-support/cases`：查看人工承接队列。
- `GET /api/customer-support/cases/{id}`：查看脱敏摘要、证据与会话记录。
- `POST /api/customer-support/cases/{id}/assign`、`/resolve`：条件更新状态与归属，拒绝并发覆盖。

## 确定性意图与证据

路由按关键字、订单号格式和请求结构确定为以下类型：

- `CATALOG`：检索 `CustomerCatalogChunk`；优先使用既有 512 维向量索引，失败时明确降级或转人工，不静默使用无关来源。
- `ORDER_STATUS`：只读查询当前登录用户的 `Order` 与 `ReturnRequest`；订单不属于当前用户时不暴露存在性。
- `AFTER_SALES_POLICY`：检索经过批准的售后规则知识库，附来源。
- `ACTION_REQUEST`、`AMBIGUOUS`、`UNSAFE`、`NO_EVIDENCE`：不执行写操作，创建或建议人工承接。

生成模型只接收脱敏消息、最近有限轮次的脱敏会话摘要、当前用户可读的结构化订单摘要和检索证据。回复必须引用证据；模型超时、输出为空或未被证据支持时保存系统回复并转人工。

## 安全与隐私

- 先 DLP 脱敏，再持久化、检索和调用模型；安全网关拒绝注入时不调用模型。
- 当前用户只能访问自身的会话、订单、退单与客服会话工单。
- 客服和主管只读取脱敏内容；偏好仅在现有明确授权有效且属于推荐类查询时使用，并记录审计。
- 人工工单摘要只包含最小必要上下文、触发原因和资料来源，不复制原始图片、Token、密码或完整敏感材料。
- 所有副作用均使用数据库条件更新；退款与订单接口不从聊天路由调用。

## 验收与测试

实现前先编写失败测试，至少覆盖：

1. 连续两轮对话保留同一会话上下文，第二轮可引用第一轮候选商品。
2. 非会话所有者、非消费者和无 JWT 请求分别被拒绝。
3. 订单查询只能返回当前用户订单，跨用户订单不泄露。
4. 安全注入、无证据、退款执行请求和用户主动转人工均只能创建一个独立客服会话工单，不创建退款 `Ticket`。
5. DLP 后的消息、摘要和模型材料不含原始 PII；客服队列只能看到脱敏内容。
6. 并发转人工不会生成重复客服会话工单，状态流转使用条件更新。
7. 前端消息流、加载/失败/关闭状态、来源依据、人工承接卡片及移动端布局均有组件测试。
8. 后端完整测试、前端测试与生产构建通过；单容器镜像包含迁移且服务启动后可访问会话 API。

## 成功标准

消费者可在单一聊天页面完成商品、本人订单和售后政策的连续咨询；每个知识型结论都有可读证据；需要人工或执行型处理的请求生成独立、脱敏、可追踪且幂等的客服会话工单；任何退款决策仍完全由既有确定性审批流程控制。
