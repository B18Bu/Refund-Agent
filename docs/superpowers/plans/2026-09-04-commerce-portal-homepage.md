# 综合商城门户首页实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将消费者商城首页改为参考图所示的多层导航与三栏综合商城门户，同时继续展示 vivo/小米真实目录。

**架构：** `CustomerShell` 负责工具栏、搜索栏和主导航；`ShopHome` 负责从已加载商品推导类目、生成三栏首屏与商品区。所有商品、价格、可售性和订单数据继续由现有 API 提供。

**技术栈：** React 18、TypeScript、Ant Design、React Router、Vitest、CSS Grid。

---

## 文件边界

- `frontend/src/components/CustomerShell.tsx`：工具栏、搜索栏和红色主导航。
- `frontend/src/pages/ShopHome.tsx`：分类菜单、主会场、服务面板与商品区。
- `frontend/src/pages/ShopHome.test.tsx`：主页真实分类和关键门户区块测试。
- `frontend/src/styles.css`：仅消费者首页的三栏及响应式样式。

### 任务 1：门户首页结构测试

**文件：**
- 修改：`frontend/src/pages/ShopHome.test.tsx`
- 修改：`frontend/src/pages/ShopHome.tsx`

- [ ] **步骤 1：编写失败测试**

```tsx
expect(await screen.findByRole('navigation', { name: '全部商品分类' })).toBeInTheDocument()
expect(screen.getByRole('region', { name: '商城主会场' })).toBeInTheDocument()
expect(screen.getByRole('complementary', { name: '用户服务' })).toBeInTheDocument()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- --run src/pages/ShopHome.test.tsx`

预期：FAIL，当前首页没有三栏门户语义区域。

- [ ] **步骤 3：实现真实数据驱动三栏首屏**

```tsx
const featuredProduct = items.find((product) => product.image_url) || items[0]
<section className="portal-stage">
  <nav aria-label="全部商品分类">…</nav>
  <section aria-label="商城主会场">…</section>
  <aside aria-label="用户服务">…</aside>
</section>
```

分类仅来自 `categories`；主会场使用 `featuredProduct.image_url` 或中性背景；服务面板仅链接 `/shop/orders`、`/shop/returns` 和 `/shop/cart`。

- [ ] **步骤 4：运行测试验证通过**

运行：`npm --prefix frontend test -- --run src/pages/ShopHome.test.tsx`

预期：PASS。

- [ ] **步骤 5：提交**

运行：`git add frontend/src/pages/ShopHome.tsx frontend/src/pages/ShopHome.test.tsx; git commit -m "feat: 增加商城门户三栏首页"`

### 任务 2：多层导航与响应式样式

**文件：**
- 修改：`frontend/src/components/CustomerShell.tsx`
- 修改：`frontend/src/styles.css`

- [ ] **步骤 1：编写失败测试**

```tsx
expect(screen.getByRole('navigation', { name: '商城主导航' })).toBeInTheDocument()
expect(screen.getByText('真实目录')).toBeInTheDocument()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- --run src/pages/ShopHome.test.tsx`

预期：FAIL，现有壳层没有主导航语义或事实性目录提示。

- [ ] **步骤 3：实现样式与可访问导航**

为工具栏、品牌搜索栏和主导航添加语义容器；CSS 使用 `220px minmax(0, 1fr) 290px` 的桌面三栏，`900px` 以下改为两列，`640px` 以下改为单列。所有不可用业务入口不渲染，焦点状态保持可见。

- [ ] **步骤 4：运行测试和构建**

运行：`npm --prefix frontend test -- --run; npm --prefix frontend run build`

预期：全部 React 测试 PASS，构建 exit code 0。

- [ ] **步骤 5：提交**

运行：`git add frontend/src/components/CustomerShell.tsx frontend/src/pages/ShopHome.tsx frontend/src/pages/ShopHome.test.tsx frontend/src/styles.css; git commit -m "feat: 重构综合商城门户导航"`

### 任务 3：运行态与商城回归验收

**文件：**
- 修改：`frontend/src/styles.css`（仅修复验收发现的门户响应式问题）

- [ ] **步骤 1：运行后端商城回归**

运行：`.venv\Scripts\python.exe -m pytest backend/tests/test_shop_api.py backend/tests/test_role_isolated_e2e.py -q`

预期：全部 PASS。

- [ ] **步骤 2：重建前端并验证响应**

运行：`docker compose -f deploy/compose/docker-compose.yml up -d --build frontend`，访问 `http://localhost` 和 `http://localhost:8001/healthz`。

预期：前端容器运行、首页返回新哈希资源、健康接口返回 `{"status":"ok"}`。

- [ ] **步骤 3：提交验收修复（若有）**

运行：`git add frontend/src/styles.css; git commit -m "fix: 修正商城门户响应式展示"`
