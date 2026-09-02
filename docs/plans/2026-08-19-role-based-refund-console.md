# 角色化退款控制台实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为客服与主管构建角色化退款控制台，提供安全的数据隔离、左侧导航、主管实时监控和退款流程说明页。

**架构：** 后端在工单列表与详情接口统一执行角色过滤；前端以共享 `AppShell` 承载角色菜单、默认路由和状态徽标，`Monitor` 负责待处理优先的主管视图，`ProcessOverview` 负责静态流程说明。沿用现有 Ant Design、axios、5 秒轮询及 SSE 能力，不改变退款决策规则。

**技术栈：** FastAPI、SQLAlchemy、pytest；React 18、TypeScript、Ant Design、React Router、axios、Vite。

---

## 文件清单

- 创建：`frontend/src/types/auth.ts`，定义角色与本地会话读取类型。
- 创建：`frontend/src/components/AppShell.tsx`，实现登录后统一外壳、角色菜单、动态徽标与退出登录。
- 创建：`frontend/src/components/StatusLegend.tsx`，复用状态颜色和中文标签。
- 创建：`frontend/src/pages/Monitor.tsx`，主管待处理优先实时监控。
- 创建：`frontend/src/pages/ProcessOverview.tsx`，标准退款流程说明。
- 创建：`frontend/src/pages/MyTickets.tsx`，客服自己的申请列表，复用工作台建单能力。
- 修改：`frontend/src/App.tsx`，增加角色默认跳转与新页面路由。
- 修改：`frontend/src/pages/Login.tsx`，登录后按 JWT 角色跳转。
- 修改：`frontend/src/pages/Dashboard.tsx`，迁移为统一外壳内的主管/通用工作台内容。
- 修改：`frontend/src/pages/TicketDetail.tsx`，接入统一外壳并处理无权限/不存在响应。
- 修改：`frontend/src/pages/Screen.tsx`，接入统一外壳并限制主管入口。
- 修改：`frontend/src/api/client.ts`，提供角色读取与统一退出辅助函数（仅在现有拦截器基础上扩展）。
- 修改：`backend/app/routers/tickets.py:151-215`，列表与详情按角色过滤。
- 修改：`backend/tests/test_tickets_api.py`，增加客服隔离、主管全量和详情越权测试。

---

### 任务 1：先固定后端角色隔离行为

**文件：**
- 修改：`backend/tests/test_tickets_api.py`
- 修改：`backend/app/routers/tickets.py:151-215`

- [ ] **步骤 1：阅读现有测试夹具并编写失败测试**

在现有 API 测试模块中沿用登录与测试数据库夹具，增加三个行为断言：客服登录后 `GET /api/tickets` 不包含主管或其他客服创建的工单；主管登录后包含全部工单；客服请求他人 `GET /api/tickets/{id}` 返回 404。测试数据至少创建两个用户和两条工单，断言接口结果中的 `ticket_no` 集合，而不是仅断言响应码。

```python
def test_customer_service_only_sees_own_tickets(client, db):
    cs1, cs2, sv1 = seed_users(db)
    own = seed_ticket(db, user_id=cs1.id, ticket_no="own")
    other = seed_ticket(db, user_id=cs2.id, ticket_no="other")
    login_as(client, cs1)
    response = client.get("/api/tickets")
    assert response.status_code == 200
    assert [row["ticket_no"] for row in response.json()] == ["own"]
    assert client.get(f"/api/tickets/{other.id}").status_code == 404


def test_supervisor_sees_all_tickets(client, db):
    cs1, cs2, sv1 = seed_users(db)
    seed_ticket(db, user_id=cs1.id, ticket_no="cs1-ticket")
    seed_ticket(db, user_id=cs2.id, ticket_no="cs2-ticket")
    login_as(client, sv1)
    response = client.get("/api/tickets")
    assert {row["ticket_no"] for row in response.json()} == {"cs1-ticket", "cs2-ticket"}
```

如果模块没有上述夹具，先按该文件已有的 `TestClient`、数据库覆盖和密码种子方式实现等价的本地夹具；不要引入新的测试框架。

- [ ] **步骤 2：运行测试确认当前实现失败**

运行：

```powershell
cd backend
pytest tests/test_tickets_api.py -k "only_sees_own or sees_all" -v
```

预期：客服隔离测试失败，因为当前列表查询没有 `user_id` 条件；详情越权测试失败，因为当前详情只按工单 ID 查询。

- [ ] **步骤 3：实现最少的查询过滤**

在 `list_tickets` 和 `get_ticket` 中按角色添加过滤，主管保持全量，客服限定 `Ticket.user_id == user.id`；详情无权访问时统一返回现有中文 404 错误。不要修改审批权限或响应字段。

```python
query = db.query(Ticket)
if user.role != Role.SV:
    query = query.filter(Ticket.user_id == user.id)
rows = query.order_by(Ticket.id.desc()).limit(100).all()
```

- [ ] **步骤 4：运行后端测试确认通过**

运行：

```powershell
pytest tests/test_tickets_api.py -v
```

预期：新增隔离测试和该模块原有测试全部 PASS。

- [ ] **步骤 5：Commit**

```powershell
git add backend/app/routers/tickets.py backend/tests/test_tickets_api.py
git commit -m "feat: enforce ticket visibility by role"
```

### 任务 2：建立前端会话与统一应用外壳

**文件：**
- 创建：`frontend/src/types/auth.ts`
- 创建：`frontend/src/components/AppShell.tsx`
- 创建：`frontend/src/components/StatusLegend.tsx`
- 修改：`frontend/src/api/client.ts`

- [ ] **步骤 1：编写角色解析与导航行为测试/检查清单**

如果项目当前无前端测试框架，不为本次功能引入大规模测试基础设施；先在实现前记录可执行验收：JWT payload 的 `role` 为 `sv` 时显示实时监控、待人工审批、数据大屏；`cs` 时只显示退款工作台、我的申请、退款流程总览；退出清除 token 并跳转 `/login`。

- [ ] **步骤 2：实现最少的会话类型与解析函数**

在 `auth.ts` 中定义 `Role = 'cs' | 'sv'`、`SessionUser`，实现只读取 JWT payload 的非敏感 `role` 和 `sub`，解析失败返回 `null`。JWT 仅用于界面导航，不作为后端授权依据。

```ts
export type Role = 'cs' | 'sv'
export type SessionUser = { id: string; role: Role }
export function getSessionUser(): SessionUser | null { /* decode payload, validate role */ }
```

- [ ] **步骤 3：实现 AppShell**

使用 Ant Design `Layout`、`Menu`、`Badge`、`Button`。菜单按 `role` 生成；主管菜单徽标来自监控数据，客服不渲染主管入口。顶部显示“客服”或“主管”、手动刷新按钮和退出按钮。通过 `Outlet` 渲染页面内容，并保留窄屏可折叠侧栏。

- [ ] **步骤 4：补充状态颜色组件**

`StatusLegend.tsx` 集中定义 `RUNNING/SUSPENDED/COMPLETED` 与 `PENDING/AUTO_REFUNDED/APPROVED/REJECTED/FAILED` 的颜色和中文文案，供工作台与监控复用；不得在此组件中请求数据。

- [ ] **步骤 5：运行类型检查**

运行：

```powershell
cd frontend
npm run build
```

预期：Vite 构建成功，无 TypeScript 错误。

- [ ] **步骤 6：Commit**

```powershell
git add frontend/src/types/auth.ts frontend/src/components/AppShell.tsx frontend/src/components/StatusLegend.tsx frontend/src/api/client.ts
git commit -m "feat: add role-based application shell"
```

### 任务 3：实现角色默认路由与页面分工

**文件：**
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/pages/Login.tsx`
- 修改：`frontend/src/pages/Dashboard.tsx`
- 创建：`frontend/src/pages/MyTickets.tsx`
- 修改：`frontend/src/pages/TicketDetail.tsx`
- 修改：`frontend/src/pages/Screen.tsx`

- [ ] **步骤 1：实现登录角色跳转**

登录成功保存 token 后读取角色：主管跳 `/monitor`，客服跳 `/my-tickets`；token 缺失时受保护路由重定向 `/login`。

- [ ] **步骤 2：实现路由表**

将 `/` 改为角色重定向；增加 `/workspace`、`/my-tickets`、`/monitor`、`/process`；将 `/screen` 和 `/ticket/:id` 放入 `AppShell`，由组件内权限控制或路由守卫限制主管入口。保留 `/login` 和通配重定向。

```tsx
<Route element={<RequireSession />}>
  <Route element={<AppShell />}>
    <Route path="/" element={<RoleHomeRedirect />} />
    <Route path="/workspace" element={<Dashboard />} />
    <Route path="/my-tickets" element={<MyTickets />} />
    <Route path="/monitor" element={<Monitor />} />
    <Route path="/process" element={<ProcessOverview />} />
    <Route path="/ticket/:id" element={<TicketDetail />} />
    <Route path="/screen" element={<Screen />} />
  </Route>
</Route>
```

- [ ] **步骤 3：迁移工作台与客服申请页**

保留现有 `Dashboard` 的建单 Modal、上传限制、幂等请求和列表字段；将工作台路径改为 `/workspace`。`MyTickets` 复用同一建单与表格结构，但标题改为“我的退款申请”，数据直接使用后端已过滤列表，不再做前端全量筛选。

- [ ] **步骤 4：接入详情和大屏权限错误状态**

详情页收到 404/403 时显示“无权访问该工单或工单不存在”，并提供返回申请列表按钮；`Screen` 仅主管可进入，客服访问时重定向到 `/my-tickets`。

- [ ] **步骤 5：运行构建并手工验证两角色**

运行：

```powershell
cd frontend
npm run build
```

预期：构建成功。使用 `cs1/secret123` 与 `sv1/secret123` 登录，分别确认默认页面、导航菜单和详情跳转。

- [ ] **步骤 6：Commit**

```powershell
git add frontend/src/App.tsx frontend/src/pages
 git commit -m "feat: split refund pages by role"
```

### 任务 4：实现主管实时监控页与导航徽标

**文件：**
- 创建：`frontend/src/pages/Monitor.tsx`
- 修改：`frontend/src/components/AppShell.tsx`
- 修改：`frontend/src/api/client.ts`（仅在需要共享刷新/请求错误辅助时）

- [ ] **步骤 1：定义监控统计函数并写失败检查**

从 `/tickets` 响应计算 `FAILED` 异常数、`SUSPENDED` 待审批数、`RUNNING` 处理中数、总申请金额及优先队列；断言失败工单进入异常队列、待审批工单进入审批队列，不能仅按 `status` 判断失败。

```ts
const failed = rows.filter((row) => row.outcome === 'FAILED').length
const pending = rows.filter((row) => row.status === 'SUSPENDED').length
const running = rows.filter((row) => row.status === 'RUNNING').length
const priority = rows.filter((row) => row.outcome === 'FAILED' || row.status === 'SUSPENDED')
```

- [ ] **步骤 2：实现监控首屏**

使用 Ant Design `Card`、`List`、`Tag`、`Alert`、`Statistic`；顶部显示“自动更新中”、最近更新时间和刷新按钮；异常卡片红色、待审批橙色、处理中蓝色。优先队列每行可导航到 `/ticket/:id`，待审批行显示“去审批”。

- [ ] **步骤 3：实现轮询、变化检测和中文提示**

沿用 5 秒刷新；保留上一次异常/待审批订单 ID 集合，只在新 ID 出现时调用 `message.warning` 或 `message.error` 一次。请求失败时显示“数据加载失败，可重试”，不显示“自动更新中”。加载成功后更新最近时间。

- [ ] **步骤 4：实现流程状态概览**

根据 `status` 展示提交申请、处理中、待审批、已完成等数量；不要把这些统计描述为精确的内部 Agent 节点，因为 `/tickets` 列表没有节点字段。

- [ ] **步骤 5：完成导航徽标联动**

`AppShell` 共享监控查询或接收监控统计，通过 `Badge` 显示异常和待审批数量；请求失败时隐藏徽标并在监控页展示错误，不显示过期数字。

- [ ] **步骤 6：运行构建与实时场景验证**

运行：

```powershell
cd frontend
npm run build
```

预期：构建成功。主管登录后确认 `/monitor` 显示待办卡片、优先队列、手动刷新和自动更新状态；新增或状态改变工单后 5 秒内更新且只提示一次。

- [ ] **步骤 7：Commit**

```powershell
git add frontend/src/pages/Monitor.tsx frontend/src/components/AppShell.tsx frontend/src/api/client.ts
git commit -m "feat: add supervisor refund monitoring"
```

### 任务 5：实现退款流程总览页

**文件：**
- 创建：`frontend/src/pages/ProcessOverview.tsx`

- [ ] **步骤 1：实现标准流程说明**

使用 Ant Design `Steps` 或自定义响应式步骤卡片，固定展示：提交申请、凭证 OCR、风险分析、舆情分析、金额决策、自动退赔/人工审批/处理失败。每一步提供中文名称、作用和可能结果；页面不请求工单数据。

- [ ] **步骤 2：补充响应式布局和状态说明**

桌面端使用横向步骤，窄屏改为纵向步骤；底部用统一状态颜色说明自动退赔、人工审批、失败三种结果，并提供返回工作台按钮。

- [ ] **步骤 3：运行构建**

运行：

```powershell
cd frontend
npm run build
```

预期：构建成功，页面不产生横向溢出。

- [ ] **步骤 4：Commit**

```powershell
git add frontend/src/pages/ProcessOverview.tsx
git commit -m "feat: add refund process overview"
```

### 任务 6：端到端验收与回归

**文件：**
- 修改：`backend/tests/test_tickets_api.py`（若回归发现缺口）
- 修改：`frontend/src/**`（仅修复验收发现的问题）

- [ ] **步骤 1：运行后端完整测试**

运行：

```powershell
cd backend
pytest tests/ -v
```

预期：原有测试与角色隔离测试全部通过；如果环境没有 Redis，仅允许现有标记的真实 Redis 测试跳过，并在结果中明确记录。

- [ ] **步骤 2：运行前端构建**

运行：

```powershell
cd frontend
npm run build
```

预期：构建成功，无 TypeScript 或 Vite 错误。

- [ ] **步骤 3：启动全栈并验证核心路径**

运行：

```powershell
docker compose up -d --build
```

验证：主管登录默认进入实时监控；异常和待审批显示红/橙徽标；工作台可查看全部订单；客服默认进入我的申请且不能看到他人订单；流程总览仅展示标准链路；客服直接访问他人详情被拒绝；退出后回到登录页。

- [ ] **步骤 4：记录失败和跳过项**

若 Docker、Redis、SSE 或 OCR 环境不可用，记录具体命令输出和跳过原因，不将未验证项标记为通过。

- [ ] **步骤 5：Commit 验收修复**

```powershell
git add backend frontend
 git commit -m "test: verify role-based refund console"
```
