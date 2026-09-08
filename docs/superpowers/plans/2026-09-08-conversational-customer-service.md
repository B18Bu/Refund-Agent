# 对话式智能客服实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将单轮商品咨询升级为带证据、多轮会话、订单/售后查询和独立人工承接工单的对话式智能客服。

**架构：** 新增客服会话、消息和人工承接工单表，所有持久化文本先经 DLP 脱敏。`CustomerAssistantService` 以确定性意图路由选择商品 RAG、当前用户订单或售后政策证据，再生成受约束回复。聊天模型没有任何写业务数据的工具权限；转人工只创建独立客服工单。

**技术栈：** FastAPI、SQLAlchemy、PostgreSQL、Redis、React、TypeScript、Ant Design、Vitest、pytest。

---

## 文件结构

- 创建：`backend/migrations/20260908_add_customer_support.sql`，显式创建客服会话、消息和人工承接表及索引。
- 修改：`backend/app/customer_assistant/models.py`，注册会话、消息和客服工单 ORM 模型及受限枚举。
- 创建：`backend/app/customer_assistant/conversations.py`，实现会话归属、脱敏消息持久化、确定性路由、证据组织和幂等转人工。
- 修改：`backend/app/customer_assistant/schemas.py`、`backend/app/customer_assistant/service.py`，定义会话 API 契约并把原商品目录答复复用为 `CATALOG` 证据提供者。
- 修改：`backend/app/routers/customer_assistant.py`，增加消费者会话 API；创建：`backend/app/routers/customer_support.py`，增加客服/主管人工队列 API；修改：`backend/app/main.py` 注册路由。
- 创建：`backend/tests/test_customer_support_conversations.py`、`backend/tests/test_customer_support_api.py`，覆盖会话、多租户、DLP、订单隔离、转人工幂等和 RBAC。
- 修改：`frontend/src/pages/CustomerAssistant.tsx`、`frontend/src/types/shop.ts`、`frontend/src/api/client.ts`，实现会话侧栏、消息流、发送、依据与人工承接状态。
- 修改：`frontend/src/components/CustomerShell.tsx`、`frontend/src/styles.css`；创建：`frontend/src/pages/CustomerAssistant.test.tsx` 的对话流断言。
- 修改：`deploy/single-container/entrypoint.sh` 和 `backend/tests/test_single_container_deployment.py`，使单容器启动前执行新迁移。

### 任务 1：数据库模型与迁移

**文件：**
- 创建：`backend/migrations/20260908_add_customer_support.sql`
- 修改：`backend/app/customer_assistant/models.py`
- 修改：`backend/app/models.py`
- 测试：`backend/tests/test_customer_support_conversations.py`

- [ ] **步骤 1：编写失败的迁移和模型测试**

```python
def test_customer_support_case_is_distinct_from_refund_ticket(db_session):
    conversation = CustomerSupportConversation(user_id=customer.id)
    db_session.add(conversation)
    db_session.commit()
    case = CustomerSupportCase.create_once(db_session, conversation, "USER_REQUEST")
    assert case.conversation_id == conversation.id
    assert db_session.query(Ticket).count() == 0
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest backend/tests/test_customer_support_conversations.py::test_customer_support_case_is_distinct_from_refund_ticket -q`

预期：失败，原因是客服会话模型尚未定义。

- [ ] **步骤 3：创建最小显式迁移和模型**

```sql
CREATE TABLE customer_support_conversations (... user_id INTEGER NOT NULL REFERENCES users(id), status VARCHAR(16) NOT NULL, ...);
CREATE TABLE customer_support_messages (... content_masked TEXT NOT NULL, evidence JSON NOT NULL DEFAULT '{}', ...);
CREATE TABLE customer_support_cases (... conversation_id INTEGER NOT NULL UNIQUE REFERENCES customer_support_conversations(id), ...);
```

```python
class CustomerSupportCase(Base):
    __tablename__ = "customer_support_cases"
    conversation_id: Mapped[int] = mapped_column(ForeignKey("customer_support_conversations.id"), unique=True)
```

- [ ] **步骤 4：运行测试验证通过并检查迁移顺序**

运行：`python -m pytest backend/tests/test_customer_support_conversations.py -q`

预期：通过；不调用 `create_all` 创建新表。

### 任务 2：会话服务与确定性意图

**文件：**
- 创建：`backend/app/customer_assistant/conversations.py`
- 修改：`backend/app/customer_assistant/service.py`
- 测试：`backend/tests/test_customer_support_conversations.py`

- [ ] **步骤 1：编写失败的多轮、订单隔离和 DLP 测试**

```python
def test_second_turn_receives_masked_prior_message_and_catalog_evidence(db_session):
    conversation = service.create_conversation(customer)
    service.reply(conversation, customer, "推荐拍照手机")
    reply = service.reply(conversation, customer, "它和上一款夜拍谁更好")
    assert reply.conversation_id == conversation.id
    assert reply.history_count == 2

def test_order_lookup_never_returns_another_customers_order(db_session):
    reply = service.reply(conversation, customer, f"查询订单 {other_order.order_no}")
    assert other_order.order_no not in reply.answer
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest backend/tests/test_customer_support_conversations.py -q`

预期：失败，原因是会话服务和意图路由不存在。

- [ ] **步骤 3：实现受限服务**

```python
def route_intent(message: str) -> SupportIntent:
    if _ACTION_REQUEST_RE.search(message): return SupportIntent.ACTION_REQUEST
    if _ORDER_RE.search(message): return SupportIntent.ORDER_STATUS
    if _AFTER_SALES_RE.search(message): return SupportIntent.AFTER_SALES_POLICY
    return SupportIntent.CATALOG

def reply(self, conversation, user, message):
    masked, _ = DLP.mask(message)
    self._critic.block_or_raise(masked, settings.SECURITY_INJECTION_THRESHOLD)
    intent = route_intent(masked)
    return self._persist_reply(conversation, intent, self._read_only_evidence(user, intent, masked))
```

- [ ] **步骤 4：运行服务测试验证通过**

运行：`python -m pytest backend/tests/test_customer_support_conversations.py -q`

预期：通过；测试确认模型材料、消息和人工摘要均无原始 PII。

### 任务 3：消费者会话 API 与人工客服队列

**文件：**
- 修改：`backend/app/customer_assistant/schemas.py`
- 修改：`backend/app/routers/customer_assistant.py`
- 创建：`backend/app/routers/customer_support.py`
- 修改：`backend/app/main.py`
- 测试：`backend/tests/test_customer_support_api.py`

- [ ] **步骤 1：编写失败的 API 契约测试**

```python
def test_customer_can_only_read_own_conversation(client, db_session):
    response = client.get(f"/api/customer-assistant/conversations/{other_id}", headers=customer_headers)
    assert response.status_code == 404

def test_escalation_is_idempotent_and_does_not_create_refund_ticket(client, db_session):
    first = client.post(f"/api/customer-assistant/conversations/{conversation_id}/escalations", headers=headers)
    second = client.post(f"/api/customer-assistant/conversations/{conversation_id}/escalations", headers=headers)
    assert first.json()["case_id"] == second.json()["case_id"]
    assert db_session.query(Ticket).count() == 0
```

- [ ] **步骤 2：运行 API 测试验证失败**

运行：`python -m pytest backend/tests/test_customer_support_api.py -q`

预期：失败，原因是新路由不存在。

- [ ] **步骤 3：实现严格的接口与条件更新**

```python
@router.post("/conversations/{conversation_id}/escalations")
def escalate(conversation_id: int, user=Depends(require_role(Role.CUSTOMER)), db: Session = Depends(get_db)):
    return serialize_case(ConversationService(db).escalate(conversation_id, user.id, "USER_REQUEST"))

@router.post("/cases/{case_id}/assign")
def assign(case_id: int, user=Depends(require_roles(Role.CS, Role.SV)), db: Session = Depends(get_db)):
    return serialize_case(SupportCaseService(db).assign_open_case(case_id, user.id))
```

- [ ] **步骤 4：运行 API 测试验证通过**

运行：`python -m pytest backend/tests/test_customer_support_api.py backend/tests/test_customer_assistant_api.py -q`

预期：通过；跨用户会话返回 404，CS/SV 队列仅显示脱敏记录。

### 任务 4：聊天前端与人工承接界面

**文件：**
- 修改：`frontend/src/pages/CustomerAssistant.tsx`
- 修改：`frontend/src/types/shop.ts`
- 修改：`frontend/src/styles.css`
- 测试：`frontend/src/pages/CustomerAssistant.test.tsx`

- [ ] **步骤 1：编写失败的组件测试**

```tsx
it('keeps prior messages and renders an escalation action', async () => {
  render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '发送' }))
  expect(await screen.findByText('第一轮答复')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '转人工' })).toBeInTheDocument()
})
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`

预期：失败，原因是当前页面只保留单次 `reply`。

- [ ] **步骤 3：实现连续消息流**

```tsx
const [conversation, setConversation] = useState<CustomerSupportConversation | null>(null)
const [messages, setMessages] = useState<CustomerSupportMessage[]>([])
const send = async () => {
  const response = await client.post(`/customer-assistant/conversations/${conversation!.id}/messages`, { message })
  setMessages(response.data.messages)
}
```

- [ ] **步骤 4：运行前端测试和构建验证通过**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`

运行：`npm --prefix frontend run build`

预期：测试与生产构建均通过，移动端无水平溢出。

### 任务 5：单容器迁移与全量验收

**文件：**
- 修改：`deploy/single-container/entrypoint.sh`
- 修改：`backend/tests/test_single_container_deployment.py`
- 测试：`backend/tests/test_deploy_migrations.py`

- [ ] **步骤 1：编写失败的启动顺序测试**

```python
def test_entrypoint_runs_customer_support_migration_before_supervisor():
    content = ENTRYPOINT.read_text(encoding="utf-8")
    assert content.index("20260908_add_customer_support.sql") < content.index("exec supervisord")
```

- [ ] **步骤 2：运行部署测试验证失败**

运行：`python -m pytest backend/tests/test_single_container_deployment.py backend/tests/test_deploy_migrations.py -q`

预期：失败，原因是迁移未在单容器入口注册。

- [ ] **步骤 3：在现有有序迁移列表中添加新迁移**

```sh
run_migration /app/migrations/20260908_add_customer_support.sql
exec supervisord -c /etc/supervisor/conf.d/app.conf
```

- [ ] **步骤 4：执行完整验证**

运行：`docker compose -f deploy/compose/docker-compose.yml up -d --build app`

运行：`docker exec -e ENVIRONMENT=testing -e LLM_PROVIDER=mock compose-app-1 /opt/venv/bin/python -m pytest tests -q`

运行：`npm --prefix frontend test -- --run`

运行：`npm --prefix frontend run build`

预期：容器只包含一个 `app` 服务，所有后端测试、前端测试和生产构建通过，`/healthz` 返回 200。
