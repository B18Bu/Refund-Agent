# 多标签登录与智能客服历史会话实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让同浏览器标签页独立登录不同角色，并让顾客查看、选择和继续自己的历史智能客服会话。

**架构：** 前端抽出基于 `sessionStorage` 的 Token 存储入口，所有认证读写均调用它。后端基于已有会话、消息和人工工单表提供只读的当前用户会话摘要；客服浮窗在默认收起的侧栏中读取摘要、选择会话并加载现有消息接口。

**技术栈：** React、TypeScript、Axios、FastAPI、SQLAlchemy、Pytest、Vitest。

---

## 文件结构

- 创建：`frontend/src/auth/session.ts` — 当前标签页 Token 的唯一读写入口。
- 修改：`frontend/src/api/client.ts` — 请求鉴权与 401 清理调用会话入口。
- 修改：`frontend/src/types/auth.ts`、`frontend/src/pages/Login.tsx`、`frontend/src/components/AppShell.tsx` — 使用会话入口读取、写入和清理身份。
- 修改：`backend/app/customer_assistant/conversations.py` — 当前用户会话摘要查询。
- 修改：`backend/app/customer_assistant/schemas.py`、`backend/app/routers/customer_assistant.py` — 受 RBAC 保护的历史列表契约与路由。
- 修改：`frontend/src/types/shop.ts`、`frontend/src/pages/CustomerAssistant.tsx` — 历史侧栏、选中会话与只读状态。
- 修改：`frontend/src/pages/CustomerAssistant.test.tsx`、`frontend/src/pages/Login.test.tsx` — 标签页身份与侧栏 UI 回归。
- 修改：`backend/tests/test_customer_support_api.py` — 历史会话归属、排序与状态 API 回归。

### 任务 1：隔离标签页登录状态

**文件：**
- 创建：`frontend/src/auth/session.ts`
- 修改：`frontend/src/api/client.ts`
- 修改：`frontend/src/types/auth.ts`
- 修改：`frontend/src/pages/Login.tsx`
- 修改：`frontend/src/components/AppShell.tsx`
- 测试：`frontend/src/pages/Login.test.tsx`

- [ ] **步骤 1：编写失败的测试**

创建 `Login.test.tsx`，模拟登录成功后断言 Token 写入 `sessionStorage`、`localStorage` 未写入；在 `sessionStorage` 中放置客服 Token 后断言 `getSessionUser()` 返回客服角色。

```ts
expect(sessionStorage.getItem('token')).toBe('customer-token')
expect(localStorage.getItem('token')).toBeNull()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- --run src/pages/Login.test.tsx`

预期：FAIL，登录代码仍写入 `localStorage`。

- [ ] **步骤 3：实现最少代码**

创建：

```ts
export const getSessionToken = () => sessionStorage.getItem('token')
export const setSessionToken = (token: string) => sessionStorage.setItem('token', token)
export const clearSessionToken = () => sessionStorage.removeItem('token')
```

将 Axios、登录页、`getSessionUser` 和退出登录的所有 Token 操作替换为以上函数。

- [ ] **步骤 4：运行测试验证通过**

运行：`npm --prefix frontend test -- --run src/pages/Login.test.tsx`

预期：PASS。

### 任务 2：提供当前顾客历史会话列表

**文件：**
- 修改：`backend/app/customer_assistant/conversations.py`
- 修改：`backend/app/customer_assistant/schemas.py`
- 修改：`backend/app/routers/customer_assistant.py`
- 测试：`backend/tests/test_customer_support_api.py`

- [ ] **步骤 1：编写失败的测试**

创建两个顾客和三个会话，分别追加消息并创建一个 `RESOLVED` 人工工单。断言客户调用 `GET /api/customer-assistant/conversations` 只收到自己的会话，按 `updated_at` 倒序，包含最近脱敏摘要和 `NO_CASE` / `RESOLVED` 状态；客服角色调用返回 `403`。

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest backend/tests/test_customer_support_api.py -q`

预期：FAIL，路由未注册或返回 `404`。

- [ ] **步骤 3：实现最少代码**

定义响应项 `id`、`status`、`summary_masked`、`updated_at`；查询 `CustomerSupportConversation.user_id == current_user.id`，关联可选 `CustomerSupportCase`，并查询每个会话最后一条 `CustomerSupportMessage.content_masked` 作为摘要。无工单返回 `NO_CASE`。

```py
@router.get('/conversations', response_model=list[CustomerSupportConversationResponse])
def list_conversations(user=Depends(require_role(Role.CUSTOMER)), db: Session = Depends(get_db)):
    return ConversationService(db).list_conversations(user.id)
```

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest backend/tests/test_customer_support_api.py -q`

预期：PASS。

### 任务 3：显示、选择和继续历史会话

**文件：**
- 修改：`frontend/src/types/shop.ts`
- 修改：`frontend/src/pages/CustomerAssistant.tsx`
- 测试：`frontend/src/pages/CustomerAssistant.test.tsx`

- [ ] **步骤 1：编写失败的测试**

Mock 会话列表和所选会话消息，断言历史按钮初始不显示列表，点击后显示本人摘要；点击未结束会话加载消息并允许输入，点击 `RESOLVED` 会话加载消息并禁用输入。

```ts
fireEvent.click(screen.getByRole('button', { name: '历史会话' }))
expect(await screen.findByText('上次咨询夜拍')).toBeInTheDocument()
fireEvent.click(screen.getByRole('button', { name: /已结束会话/ }))
expect(screen.getByRole('textbox', { name: '输入消息' })).toBeDisabled()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`

预期：FAIL，找不到“历史会话”按钮。

- [ ] **步骤 3：实现最少代码**

在浮窗头部添加默认收起的历史会话按钮与 `aside`。打开浮窗后加载列表；选中项调用既有 `/customer-assistant/conversations/{id}/messages`，设置 `conversation`、`messages` 和关联状态。仅在状态为 `RESOLVED` 时禁用输入；继续保留人工接管轮询条件。

- [ ] **步骤 4：运行测试验证通过**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`

预期：PASS。

### 任务 4：全量相关验证与发布

**文件：** 无新增产品代码。

- [ ] **步骤 1：运行前端认证与会话回归**

运行：`npm --prefix frontend test -- --run src/pages/Login.test.tsx src/pages/CustomerAssistant.test.tsx src/pages/CustomerSupportChat.test.tsx`

预期：全部 PASS。

- [ ] **步骤 2：运行后端客服回归**

运行：`python -m pytest backend/tests/test_customer_support_api.py backend/tests/test_customer_support_conversations.py backend/tests/test_customer_assistant_api.py -q`

预期：全部 PASS。

- [ ] **步骤 3：构建前端与容器**

运行：`npm --prefix frontend run build`，然后 `docker compose --env-file .env -f deploy/compose/docker-compose.yml up -d --build`。

预期：构建退出码为 0，应用容器为 `Up`。

- [ ] **步骤 4：验证运行态**

运行：`Invoke-WebRequest -UseBasicParsing http://localhost/`。

预期：HTTP `200`。
