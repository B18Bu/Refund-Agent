# 客服订单中心与退单可见性实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让客服查看全部用户订单与全部退单，同时只允许审批既有待人工审核退单。

**架构：** 在既有 `tickets` 路由中新增受 CS/SV RBAC 保护的订单查询，并将退单队列查询从“仅挂起”扩大为“所有退单关联记录”。前端将现有退款页面扩展成含订单、退单两个页签的客服订单中心；普通订单只读，退单操作仍由服务端审批锁与状态条件更新保护。

**技术栈：** FastAPI、SQLAlchemy、Pytest、React 18、TypeScript、Ant Design、Vitest。

---

## 文件结构

- 修改：`backend/app/routers/tickets.py` — 提供客服订单列表，并返回所有关联退单的展示字段。
- 修改：`backend/tests/test_role_isolation.py` — 覆盖客服订单可见性、所有退单状态可见性和客户越权拒绝。
- 修改：`frontend/src/App.tsx` — 增加客服订单中心路由，并保留旧退款地址兼容入口。
- 修改：`frontend/src/components/AppShell.tsx` — 将客服导航入口指向订单中心。
- 修改：`frontend/src/pages/ServiceRefunds.tsx` — 实现订单/退单页签、搜索筛选、只读与可审批边界。
- 创建：`frontend/src/pages/ServiceRefunds.test.tsx` — 验证两个页签及非人工审核项无审批按钮。
- 修改：`frontend/src/pages/Orders.tsx` — 在用户订单列表显示明确的退单入口或不可申请原因。
- 修改：`frontend/src/pages/Orders.test.tsx` — 验证已支付订单的退单入口与非已支付订单提示。
- 修改：`frontend/src/styles.css` — 仅补充订单中心的淡蓝视觉和响应式布局。

### 任务 1：后端扩展客服查询范围

**文件：**
- 修改：`backend/tests/test_role_isolation.py`
- 修改：`backend/app/routers/tickets.py`

- [ ] **步骤 1：编写失败测试，要求客服查看普通订单与所有状态退单**

在 `test_role_isolation.py` 中创建一个 `PAID_SIMULATED` 普通订单，并在 `_manual_return` 返回的退单之外创建一个 `PROCESSING` 退单关联 `RUNNING` 工单；添加：

```python
def test_cs_and_sv_can_view_all_service_orders_and_return_statuses(client, db_session):
    _ticket, pending = _manual_return(db_session)
    running = _return_with_ticket_status(db_session, TicketStatus.RUNNING, "PROCESSING")
    for role in (Role.CS, Role.SV):
        headers = _headers(db_session, f"service-{role.value}", role)
        orders = client.get("/api/tickets/service/orders", headers=headers)
        returns = client.get("/api/tickets/service/returns", headers=headers)
        assert orders.status_code == returns.status_code == 200
        assert any(row["id"] == pending.order_id for row in orders.json())
        assert {row["return_no"] for row in returns.json()} >= {pending.return_no, running.return_no}
        assert {row["status"] for row in returns.json()} >= {"PENDING_REVIEW", "PROCESSING"}
    assert client.get("/api/tickets/service/orders", headers=_headers(db_session, "service-customer", Role.CUSTOMER)).status_code == 403
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest backend/tests/test_role_isolation.py::test_cs_and_sv_can_view_all_service_orders_and_return_statuses -q`

预期：FAIL，`/api/tickets/service/orders` 返回 404，且运行中的退单不在当前仅 `SUSPENDED` 的队列中。

- [ ] **步骤 3：实现最少的只读客服查询**

在 `tickets.py` 导入 `joinedload` 和 `User`。在 `list_manual_returns` 中移除 `Ticket.status == TicketStatus.SUSPENDED` 过滤，改为从 `ReturnRequest` 出发并关联 `Ticket`、`Order`、`OrderItem` 和 `User`，只返回存在 `ReturnRequest` 的记录。响应增加 `order_no`、`username`、`created_at` 与 `can_approve`，其中：

```python
"can_approve": ticket.status == TicketStatus.SUSPENDED,
"created_at": return_request.created_at.isoformat() if return_request.created_at else None,
```

新增 `GET /api/tickets/service/orders`，使用 `require_roles(Role.CS, Role.SV)`、`joinedload(Order.items)` 与 `Order.id.desc()`，并返回订单编号、用户名、金额、状态、创建时间、商品名摘要和订单明细；不得返回密码、Token 或无关工单字段。

- [ ] **步骤 4：运行测试验证通过**

运行：`pytest backend/tests/test_role_isolation.py -q`

预期：PASS，客服和主管均能读取两类列表，客户收到 403。

- [ ] **步骤 5：提交后端查询变更**

```bash
git add backend/app/routers/tickets.py backend/tests/test_role_isolation.py
git commit -m "feat: 扩展客服订单与退单查询"
```

### 任务 2：前端客服订单中心页签与权限表达

**文件：**
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/components/AppShell.tsx`
- 修改：`frontend/src/pages/ServiceRefunds.tsx`
- 创建：`frontend/src/pages/ServiceRefunds.test.tsx`
- 修改：`frontend/src/styles.css`

- [ ] **步骤 1：编写失败的页面测试**

创建 `ServiceRefunds.test.tsx`，模拟两个 API；断言进入页面后显示“订单申请”“退单申请”、普通订单的“查看详情”，并切换到退单页签后，只有 `can_approve: true` 项存在“批准退款”：

```tsx
vi.mocked(client.get).mockImplementation((url) => Promise.resolve({ data: url === '/tickets/service/orders'
  ? [{ id: 1, order_no: 'O-001', username: 'buyer', total_amount: 128, status: 'PAID_SIMULATED', items: [] }]
  : [{ id: 1, ticket_id: 8, return_no: 'R-001', status: 'PROCESSING', can_approve: false, amount: 128, evidence_paths: [], decision_reasons: [] }],
} as never))
```

- [ ] **步骤 2：运行前端测试验证失败**

运行：`npm test -- --run src/pages/ServiceRefunds.test.tsx`

工作目录：`frontend`

预期：FAIL，当前页面没有“订单申请”页签，也未请求订单列表。

- [ ] **步骤 3：实现单页双页签客服中心**

将 `ServiceRefunds.tsx` 改为使用 `Tabs`、`Input.Search`、`List` 和现有 `Alert`/`Button`。加载函数并行请求：

```tsx
const [ordersResponse, returnsResponse] = await Promise.all([
  client.get<ServiceOrder[]>('/tickets/service/orders'),
  client.get<ServiceReturn[]>('/tickets/service/returns'),
])
```

在订单页签按订单号/用户名过滤，展示商品摘要、金额、状态和只读“查看详情”信息；在退单页签按退单号/订单号/用户名过滤。将审批按钮严格写成：

```tsx
{row.can_approve && (
  <Space className="service-refunds__actions">
    <Button danger onClick={() => void approve(row.ticket_id, 'REJECT')}>驳回</Button>
    <Button type="primary" onClick={() => void approve(row.ticket_id, 'APPROVE')}>批准退款</Button>
  </Space>
)}
```

保留 `/service/refunds` 作为退单页签的兼容地址；新增 `/service/orders` 作为默认订单中心。将客服菜单改为“订单中心”，`RoleHome` 对 CS 指向 `/service/orders`。样式仅为页签筛选栏、订单卡片和移动端堆叠追加淡蓝规则。

- [ ] **步骤 4：运行前端测试和构建验证通过**

运行：`npm test -- --run src/pages/ServiceRefunds.test.tsx && npm run build`

工作目录：`frontend`

预期：测试 PASS，TypeScript 编译和 Vite build 成功。

- [ ] **步骤 5：提交客服前端变更**

```bash
git add frontend/src/App.tsx frontend/src/components/AppShell.tsx frontend/src/pages/ServiceRefunds.tsx frontend/src/pages/ServiceRefunds.test.tsx frontend/src/styles.css
git commit -m "feat: 新增客服订单中心"
```

### 任务 3：增加用户订单列表的显式退单入口

**文件：**
- 修改：`frontend/src/pages/Orders.tsx`
- 修改：`frontend/src/pages/Orders.test.tsx`
- 修改：`frontend/src/styles.css`

- [ ] **步骤 1：编写失败测试**

在 `Orders.test.tsx` 使用一条 `PAID_SIMULATED` 与一条 `CREATED` 订单，断言前者有链接文本“申请退单”且指向详情页，后者显示“支付完成后可申请退单”：

```tsx
expect(screen.getByRole('link', { name: '申请退单' })).toHaveAttribute('href', '/shop/orders/1')
expect(screen.getByText('支付完成后可申请退单')).toBeInTheDocument()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm test -- --run src/pages/Orders.test.tsx`

工作目录：`frontend`

预期：FAIL，当前列表没有显式退单入口或资格说明。

- [ ] **步骤 3：实现最少的入口与说明**

在每条订单的详情链接旁添加：

```tsx
{order.status === 'PAID_SIMULATED'
  ? <Link to={`/shop/orders/${order.id}`}>申请退单</Link>
  : <span>支付完成后可申请退单</span>}
```

保留订单详情页中现有的凭证上传、幂等键和退款弹窗，不复制退单提交逻辑。补充 `.storeflow-orders` 内操作区域的淡蓝链接与窄屏排列规则。

- [ ] **步骤 4：运行测试和构建验证通过**

运行：`npm test -- --run src/pages/Orders.test.tsx && npm run build`

工作目录：`frontend`

预期：测试 PASS，构建成功。

- [ ] **步骤 5：提交用户订单入口变更**

```bash
git add frontend/src/pages/Orders.tsx frontend/src/pages/Orders.test.tsx frontend/src/styles.css
git commit -m "feat: 增加订单退单入口"
```

### 任务 4：全量回归与容器交付

**文件：**
- 不修改源文件。

- [ ] **步骤 1：运行后端退单与权限回归**

运行：`pytest backend/tests/test_role_isolation.py backend/tests/test_returns_api.py backend/tests/test_commerce_e2e.py -q`

预期：所有测试 PASS；失败时停止并按失败用例修复，不跳过测试。

- [ ] **步骤 2：运行前端完整验证**

运行：`npm test -- --run && npm run build`

工作目录：`frontend`

预期：所有 Vitest 用例 PASS，构建成功。

- [ ] **步骤 3：重建运行镜像并检查健康状态**

运行：`docker compose up -d --build`

随后运行：`Invoke-WebRequest http://localhost:8001/healthz -UseBasicParsing | Select-Object -ExpandProperty Content`

预期：服务完成重建，健康接口返回 `{"status":"ok"}`。

- [ ] **步骤 4：检查最终工作区并提交验证日志所需代码变更**

运行：`git status --short && git log --oneline -4`

预期：仅保留用户原有的 `docs/evidence/periodic-eval-report.md`、`docs/weekly-daily-report-2026-08-29-to-09-04.md` 与 `tmp/` 未提交变更；本计划产生的代码均已在各任务提交。
