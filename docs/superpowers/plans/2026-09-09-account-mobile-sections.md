# 用户个人中心移动优先分段布局实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将用户个人中心整理为移动优先的订单与配送、收货地址、购物偏好三个清晰分段，并确保系统定义的购物偏好标签在未授权时仍可见。

**架构：** 保留 `Account.tsx` 当前的数据加载、地址 CRUD、抽屉表单和路由接口，仅调整页面语义结构与 class hook。通过 `styles.css` 为三个分段提供单列移动布局、桌面端受控双列布局和可换行的操作区域。测试以用户可见标题、状态文字、偏好授权状态及无横向溢出的布局契约为中心。

**技术栈：** React 18、TypeScript、Ant Design 5、React Testing Library、Vitest、CSS 媒体查询。

---

## 文件结构

- 修改：`frontend/src/pages/Account.test.tsx`，补充三段布局、偏好可见性和空态回归测试。
- 修改：`frontend/src/pages/Account.tsx`，保留现有业务逻辑，补充分段语义 class、操作区域标识和可读性结构。
- 修改：`frontend/src/styles.css`，重写个人中心相关样式为移动优先规则，并在桌面断点实现地址与偏好并列显示。

### 任务 1：补充个人中心布局契约测试

**文件：**
- 修改：`frontend/src/pages/Account.test.tsx`

- [ ] **步骤 1：编写失败的测试**

在现有聚合测试后增加一个桌面/移动均适用的结构契约测试，断言页面包含 `account-section--orders`、`account-section--addresses`、`account-section--preferences` 三个分段，并断言偏好接口返回 `enabled: false` 时每个系统标签仍可见且显示“未授权生成”：

```tsx
it('保持三个可扫描分段并在未授权时展示全部偏好标签', async () => {
  vi.mocked(client.get).mockResolvedValue({ data: { enabled: false, preferences: [], ignored_keys: [] } } as never)
  render(<MemoryRouter><Account /></MemoryRouter>)

  expect(await screen.findByTestId('account-section-orders')).toBeInTheDocument()
  expect(screen.getByTestId('account-section-addresses')).toBeInTheDocument()
  expect(screen.getByTestId('account-section-preferences')).toBeInTheDocument()
  expect(screen.getByText('品类')).toBeInTheDocument()
  expect(screen.getByText('购买频率')).toBeInTheDocument()
  expect(screen.getAllByText('未授权生成')).toHaveLength(6)
})
```

- [ ] **步骤 2：运行测试确认失败**

运行：`npm --prefix frontend test -- --run src/pages/Account.test.tsx`

预期：新增测试因页面尚无对应 `data-testid` 而失败；现有测试可能通过。

- [ ] **步骤 3：提交测试变更**

```bash
git add frontend/src/pages/Account.test.tsx
git commit -m "test: define account section layout contract"
```

### 任务 2：为页面增加分段语义和稳定样式钩子

**文件：**
- 修改：`frontend/src/pages/Account.tsx:23-28`

- [ ] **步骤 1：给三个 section 增加稳定标识**

在现有三个 `<section className="account-section">` 上分别增加 `account-section--orders`、`account-section--addresses`、`account-section--preferences`，并增加与测试契约一致的 `data-testid`。不改变请求、状态映射、按钮回调、地址抽屉或偏好授权判断。

```tsx
<section className="account-section account-section--orders" data-testid="account-section-orders" ...>
<section className="account-section account-section--addresses" data-testid="account-section-addresses" ...>
<section className="account-section account-section--preferences" data-testid="account-section-preferences" ...>
```

为订单列表、地址操作和偏好网格保留现有 class；仅在需要时为页头操作容器增加 `account-page__header-actions`，使窄屏按钮可独立换行。

- [ ] **步骤 2：运行目标测试确认通过**

运行：`npm --prefix frontend test -- --run src/pages/Account.test.tsx`

预期：新增结构测试和既有订单、地址、偏好测试全部 PASS。

- [ ] **步骤 3：提交页面结构变更**

```bash
git add frontend/src/pages/Account.tsx frontend/src/pages/Account.test.tsx
git commit -m "feat: add semantic account sections"
```

### 任务 3：实现移动优先和桌面自适应样式

**文件：**
- 修改：`frontend/src/styles.css:312-313`

- [ ] **步骤 1：调整基础个人中心布局**

将现有个人中心样式整理为以下行为：页面和分段使用 `min-width: 0`；页头操作可换行；订单、地址和偏好内容使用 `gap` 与可换行文本；地址操作按钮至少 `min-height: 44px`；偏好网格在默认（移动）状态为单列。

```css
.account-page { min-width: 0; }
.account-page__header-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.account-section { min-width: 0; }
.account-order p, .account-address p, .account-preference strong, .account-preference em {
  overflow-wrap: anywhere;
}
.account-address__actions .ant-btn { min-height: 44px; }
.account-preferences { grid-template-columns: 1fr; }
```

- [ ] **步骤 2：增加桌面断点布局**

在现有媒体规则中增加 `min-width: 900px` 断点：订单分段占满主列，地址和偏好分段并列；使用 `grid-column` 让订单保持主内容宽度，避免嵌套卡片或固定宽度导致横向滚动。

```css
@media (min-width: 900px) {
  .account-page { grid-template-columns: minmax(0, 1.25fr) minmax(300px, .75fr); align-items: start; }
  .account-page__header, .account-section--orders { grid-column: 1 / -1; }
  .account-section--addresses, .account-section--preferences { height: 100%; }
  .account-preferences { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
```

移动断点中将页头、分段标题和地址主体保持单列，操作区允许换行；确保 `320px` 宽度下不使用会撑开容器的固定宽度。

- [ ] **步骤 3：运行前端测试与构建**

运行：`npm --prefix frontend test -- --run src/pages/Account.test.tsx`，预期 PASS。

运行：`npm --prefix frontend run build`，预期 TypeScript 编译和 Vite 生产构建成功。

- [ ] **步骤 4：提交样式变更**

```bash
git add frontend/src/styles.css
git commit -m "style: make account page mobile first"
```

### 任务 4：完整验证与交接

**文件：**
- 验证：`frontend/src/pages/Account.tsx`
- 验证：`frontend/src/pages/Account.test.tsx`
- 验证：`frontend/src/styles.css`

- [ ] **步骤 1：运行个人中心回归测试**

运行：`npm --prefix frontend test -- --run src/pages/Account.test.tsx`

预期：所有测试通过，包含订单状态、地址入口、偏好标签和未授权状态。

- [ ] **步骤 2：运行前端生产构建**

运行：`npm --prefix frontend run build`

预期：构建退出码为 0，无 TypeScript 错误。

- [ ] **步骤 3：检查变更边界**

运行：`git diff --check` 和 `git status --short`。

预期：无空白错误；仅出现本任务涉及的三个前端文件及其提交记录，不触碰既有无关改动。

- [ ] **步骤 4：提交最终验证记录**

```bash
git add frontend/src/pages/Account.tsx frontend/src/pages/Account.test.tsx frontend/src/styles.css
git commit -m "chore: verify account center responsive layout"
```

## 规格覆盖自检

- 订单与配送、收货地址、购物偏好三段：任务 2、任务 3。
- 移动端单列、320px 至 640px 无横向滚动：任务 3、任务 4。
- 桌面端地址与偏好并列、订单保持主内容宽度：任务 3。
- 偏好标签始终可见，未授权显示状态文案：任务 1、任务 2。
- 地址新增、编辑、设为默认、删除行为不变：任务 2、任务 4。
- Ant Design 控件、焦点与至少 44px 点击区域：任务 3。
- 不修改后端接口、权限和隐私规则：任务 2 的变更边界。
