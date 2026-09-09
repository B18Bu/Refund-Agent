# 客服人工答疑与短轮询消息同步实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为客服账号建立可查看、领取和回复人工会话的工作台，并让用户端与客服端通过 2 秒短轮询双向同步脱敏消息。

**架构：** 复用 `CustomerSupportConversation`、`CustomerSupportMessage` 和 `CustomerSupportCase`，不新增数据库字段。后端在现有客服路由下增加会话消息查询与客服回复接口，使用条件更新、DLP 和角色校验；前端新增客服答疑页面并扩展智能客服浮窗，在会话打开期间以 2 秒定时器拉取消息并按消息 ID 去重。

**技术栈：** FastAPI、SQLAlchemy、Pydantic、React 18、TypeScript、Ant Design 5、Vitest、React Testing Library、pytest。

---

## 文件结构

- 修改：`backend/app/routers/customer_support.py`，增加客服会话列表过滤、消息读取和客服回复接口。
- 修改：`backend/app/customer_assistant/conversations.py`，封装会话消息查询、客服回复写入及用户归属校验。
- 修改：`backend/app/customer_assistant/schemas.py`，增加消息和客服回复请求/响应模型。
- 修改：`backend/tests/test_customer_support_conversations.py`，覆盖客服回复、DLP 脱敏、消息顺序和会话权限。
- 修改：`backend/tests/test_customer_support.py`（若文件不存在则创建），覆盖路由角色、领取冲突和关闭状态。
- 创建：`frontend/src/pages/CustomerSupportChat.tsx`，客服答疑工作台页面及 2 秒轮询。
- 创建：`frontend/src/pages/CustomerSupportChat.test.tsx`，客服工作台渲染、领取、发送和轮询测试。
- 修改：`frontend/src/components/AppShell.tsx`，为客服角色增加“人工答疑”导航入口。
- 修改：`frontend/src/App.tsx`，注册 `/service/chat` 客服路由。
- 修改：`frontend/src/components/CustomerAssistant.tsx`，转人工后轮询用户会话消息并展示人工客服回复。
- 修改：`frontend/src/types/shop.ts`，补充统一消息类型和客服会话类型。
- 修改：`frontend/src/styles.css`，增加客服工作台桌面双栏、移动单列和消息区样式。

### 任务 1：定义后端会话消息服务契约

**文件：**
- 修改：`backend/app/customer_assistant/conversations.py`
- 修改：`backend/app/customer_assistant/schemas.py`
- 测试：`backend/tests/test_customer_support_conversations.py`

- [ ] **步骤 1：编写失败测试**

增加测试，创建一个人工工单和两条消息，断言客服读取消息按 `id` 升序返回；客服回复会写入 `sender="AGENT"`，手机号被 DLP 脱敏；非所属用户读取会抛出 `LookupError`，未领取客服回复抛出 `ValueError`。

```python
def test_agent_reply_is_masked_and_requires_assignment(db_session):
    conversation, case, customer, agent = seed_open_case(db_session)
    service = ConversationService(db_session)
    with pytest.raises(ValueError):
        service.add_agent_message(case.id, agent.id, "请联系 13812340000")
    case.status = "IN_PROGRESS"
    case.assigned_to = agent.id
    db_session.commit()
    message = service.add_agent_message(case.id, agent.id, "请联系 13812340000")
    assert message.sender == "AGENT"
    assert "13812340000" not in message.content_masked
    assert "138****0000" in message.content_masked
```

- [ ] **步骤 2：运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest backend/tests/test_customer_support_conversations.py -q`

预期：因 `add_agent_message` 尚未定义而失败。

- [ ] **步骤 3：实现最小服务方法和模型**

新增 `list_messages(conversation_id, user_id, role)`、`add_agent_message(case_id, agent_id, content)` 和 `conversation_for_customer`；消息响应包含 `id`、`sender`、`content`、`evidence`、`created_at`。客服回复必须检查 `IN_PROGRESS` 与 `assigned_to`，调用 `DLP.mask` 后写入。

- [ ] **步骤 4：运行测试确认通过**

运行同上，预期新增服务测试 PASS，既有会话测试保持 PASS。

- [ ] **步骤 5：提交**

```bash
git add backend/app/customer_assistant/conversations.py backend/app/customer_assistant/schemas.py backend/tests/test_customer_support_conversations.py
git commit -m "feat: add support conversation message service"
```

### 任务 2：增加客服和用户消息 API

**文件：**
- 修改：`backend/app/routers/customer_support.py`
- 修改：`backend/app/routers/customer_assistant.py`
- 测试：`backend/tests/test_customer_support.py`

- [ ] **步骤 1：编写失败 API 测试**

测试 `GET /api/customer-support/cases` 只返回 `OPEN`、`IN_PROGRESS`；测试客服领取后 `POST /cases/{id}/messages` 返回 `AGENT` 消息；测试用户 `GET /conversations/{id}/messages` 可读取自己的消息，其他用户返回 404。

```python
def test_customer_support_message_round_trip(api_client, customer_token, agent_token):
    case = create_escalated_case(api_client, customer_token)
    api_client.post(f"/api/customer-support/cases/{case['id']}/assign", headers=agent_token)
    response = api_client.post(
        f"/api/customer-support/cases/{case['id']}/messages",
        headers=agent_token,
        json={"content": "已为你查询订单"},
    )
    assert response.status_code == 200
    assert response.json()["sender"] == "AGENT"
```

- [ ] **步骤 2：运行测试确认失败**

运行：`.venv\Scripts\python.exe -m pytest backend/tests/test_customer_support.py -q`

预期：新接口返回 404。

- [ ] **步骤 3：实现路由和权限**

增加 `GET /cases/{case_id}/messages`、`POST /cases/{case_id}/messages` 和 `GET /conversations/{conversation_id}/messages`。客服路由仅允许 `CS/SV`；客服回复仅允许当前领取人；用户路由仅允许会话所属 `CUSTOMER`。列表过滤仅保留 `OPEN`、`IN_PROGRESS`，并返回摘要、更新时间和未读所需字段。

- [ ] **步骤 4：运行后端定向测试**

运行：`.venv\Scripts\python.exe -m pytest backend/tests/test_customer_support.py backend/tests/test_customer_support_conversations.py -q`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add backend/app/routers/customer_support.py backend/app/routers/customer_assistant.py backend/tests/test_customer_support.py
git commit -m "feat: expose support chat message APIs"
```

### 任务 3：构建客服答疑工作台

**文件：**
- 创建：`frontend/src/pages/CustomerSupportChat.tsx`
- 创建：`frontend/src/pages/CustomerSupportChat.test.tsx`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/components/AppShell.tsx`
- 修改：`frontend/src/types/shop.ts`

- [ ] **步骤 1：编写失败组件测试**

测试页面加载会话列表，显示客户标识、摘要和状态；点击“领取会话”调用 assign；领取成功后加载消息并发送回复；发送按钮在空消息时禁用。

```tsx
it('领取人工会话并发送客服回复', async () => {
  vi.mocked(client.get).mockResolvedValue({ data: [{ id: 3, conversation_id: 9, status: 'OPEN', summary_masked: '用户咨询订单', assigned_to: null }] } as never)
  vi.mocked(client.post).mockResolvedValue({ data: { id: 11, sender: 'AGENT', content: '我来帮你查询', evidence: {} } } as never)
  render(<MemoryRouter><CustomerSupportChat /></MemoryRouter>)
  expect(await screen.findByText('用户咨询订单')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '领取会话' }))
  fireEvent.change(screen.getByRole('textbox', { name: '客服回复' }), { target: { value: '我来帮你查询' } })
  fireEvent.click(screen.getByRole('button', { name: '发送回复' }))
  expect(await screen.findByText('我来帮你查询')).toBeInTheDocument()
})
```

- [ ] **步骤 2：运行测试确认失败**

运行：`npm --prefix frontend test -- --run src/pages/CustomerSupportChat.test.tsx`

预期：因页面组件尚不存在而失败。

- [ ] **步骤 3：实现页面和路由**

实现左侧会话列表、右侧消息区、领取/结束操作、当前客服只读限制和 2 秒 `setInterval`；组件卸载时清除定时器，轮询失败不清空已有消息。将 `/service/chat` 加入客服导航，保持主管和消费者路由不变。

- [ ] **步骤 4：运行组件测试**

运行同上，预期组件测试 PASS。

- [ ] **步骤 5：提交**

```bash
git add frontend/src/pages/CustomerSupportChat.tsx frontend/src/pages/CustomerSupportChat.test.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx frontend/src/types/shop.ts
git commit -m "feat: add customer service chat workspace"
```

### 任务 4：扩展用户端转人工消息同步

**文件：**
- 修改：`frontend/src/components/CustomerAssistant.tsx`
- 修改：`frontend/src/pages/CustomerAssistant.test.tsx`
- 修改：`frontend/src/types/shop.ts`

- [ ] **步骤 1：编写失败测试**

模拟升级接口成功后，用户端每次轮询读取会话消息；当返回 `AGENT` 消息时显示“人工客服”和回复内容；组件关闭或会话结束后不再发起轮询。

```tsx
it('转人工后轮询并展示客服回复', async () => {
  vi.useFakeTimers()
  vi.mocked(client.get).mockResolvedValue({ data: [{ id: 12, sender: 'AGENT', content: '您好，我来协助处理', evidence: {}, created_at: '2026-09-09T12:00:00Z' }] } as never)
  // 打开会话、创建并升级后推进 2 秒定时器
  vi.advanceTimersByTime(2000)
  expect(await screen.findByText('您好，我来协助处理')).toBeInTheDocument()
  vi.useRealTimers()
})
```

- [ ] **步骤 2：运行测试确认失败**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`

预期：客服消息尚未显示，测试失败。

- [ ] **步骤 3：实现轮询和状态展示**

转人工成功后启动 2 秒定时器，请求 `/customer-assistant/conversations/{id}/messages`，按消息 ID 去重并保留已有智能客服消息；将 `AGENT` 映射为“人工客服”，`SYSTEM` 映射为系统提示。会话关闭或状态为 `RESOLVED` 时清理定时器。

- [ ] **步骤 4：运行前端客服测试**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add frontend/src/components/CustomerAssistant.tsx frontend/src/pages/CustomerAssistant.test.tsx frontend/src/types/shop.ts
git commit -m "feat: sync agent replies in customer assistant"
```

### 任务 5：完善响应式样式与完整验证

**文件：**
- 修改：`frontend/src/styles.css`
- 验证：`frontend/src/pages/CustomerSupportChat.tsx`
- 验证：`frontend/src/components/CustomerAssistant.tsx`

- [ ] **步骤 1：增加工作台样式**

客服工作台桌面端使用列表 + 消息双栏，移动端单列并保留当前会话；消息气泡允许长文本换行，发送和领取按钮至少 44px，轮询状态使用文字而非颜色单独表达。

- [ ] **步骤 2：运行完整前端测试和构建**

运行：`npm --prefix frontend test -- --run`，预期全部前端测试通过。

运行：`npm --prefix frontend run build`，预期 TypeScript 与 Vite 构建退出码为 0。

- [ ] **步骤 3：运行后端相关测试**

运行：`.venv\Scripts\python.exe -m pytest backend/tests/test_customer_support.py backend/tests/test_customer_support_conversations.py -q`，预期全部通过。

- [ ] **步骤 4：检查变更边界并提交**

运行：`git diff --check` 和 `git status --short`，确认无空白错误，且不将工作区已有无关改动加入提交。

```bash
git add frontend/src/styles.css
git commit -m "style: polish customer support chat workspace"
```

## 规格覆盖自检

- 客服查看所有 `OPEN`、`IN_PROGRESS` 会话：任务 2、任务 3。
- 客服领取、回复、结束：任务 2、任务 3。
- 用户问题传递到客服端：任务 2、任务 3。
- 客服回复传递到用户端：任务 2、任务 4。
- 2 秒短轮询、去重、离开页面清理：任务 3、任务 4。
- DLP 脱敏、JWT/RBAC、会话归属和并发条件更新：任务 1、任务 2。
- 不新增数据库字段、不改变退款审批和智能推荐：任务 1、任务 2。
- 移动端单列、桌面端双栏和 44px 操作区：任务 5。
- 新增接口、状态转换、前后端轮询回归测试：任务 1 至任务 5。
