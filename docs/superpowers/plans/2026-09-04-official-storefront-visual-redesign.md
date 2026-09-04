# 官方商城前端视觉重设计实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将消费者商城改造为正式的品牌官网式电商页面，同时维持真实商品目录与现有交易安全边界。

**架构：** 保持 React Router、Axios 与 Ant Design 数据流，仅新增前端展示层的分类推导和共享商城样式。商品、价格、库存、购物车、订单和目录状态继续由原有 API 决定。

**技术栈：** React 18、TypeScript、Ant Design、React Router、CSS Grid。

---

## 文件边界

- `frontend/src/components/CustomerShell.tsx`：官网式顶部导航与可访问移动端入口。
- `frontend/src/pages/ShopHome.tsx`：首屏、分类导购、筛选和商品网格。
- `frontend/src/pages/ProductDetail.tsx`：商品详情的图片、规格与购买区。
- `frontend/src/pages/Cart.tsx`、`Checkout.tsx`、`Orders.tsx`：统一购物流程层级。
- `frontend/src/styles.css`：仅消费者商城的响应式样式；不改后台样式。
- `frontend/src/pages/ShopHome.test.tsx`：首页真实目录与分类导购测试。

### 任务 1：首页分类导购与真实来源文案

**文件：**
- 创建：`frontend/src/pages/ShopHome.test.tsx`
- 修改：`frontend/src/pages/ShopHome.tsx`

- [ ] **步骤 1：编写失败测试**

```tsx
it('只展示目录中存在的分类，并标注 vivo 与小米官方目录', async () => {
  mockGet.mockResolvedValueOnce({ data: ['vivo', 'xiaomi'] })
  mockGet.mockResolvedValueOnce({ data: { items: [xiaomiHeadset, vivoPhone] } })
  render(<MemoryRouter><ShopHome /></MemoryRouter>)
  expect(await screen.findByText('vivo · 小米官方目录')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '耳机' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '平板' })).not.toBeInTheDocument()
})
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- --run src/pages/ShopHome.test.tsx`

预期：FAIL，首页尚无小米来源文案和分类导购按钮。

- [ ] **步骤 3：实现最小分类推导**

```tsx
const categoryRules = [
  { label: '手机', keywords: ['手机', 'phone'] },
  { label: '耳机', keywords: ['耳机', 'buds', 'headphone'] },
  { label: '充电', keywords: ['充电', '电源', 'charger'] },
  { label: '数据线', keywords: ['数据线', '线'] },
]
const categories = categoryRules.filter(({ keywords }) => items.some((product) =>
  keywords.some((keyword) => product.name.toLowerCase().includes(keyword)),
))
```

分类按钮更新现有 `keyword`；将首屏文案改为 `vivo · 小米官方目录`，不创建静态商品。

- [ ] **步骤 4：运行测试验证通过**

运行：`npm --prefix frontend test -- --run src/pages/ShopHome.test.tsx`

预期：PASS。

- [ ] **步骤 5：提交**

运行：`git add frontend/src/pages/ShopHome.tsx frontend/src/pages/ShopHome.test.tsx; git commit -m "feat: 增加官方商城分类导购"`

### 任务 2：首页与导航官网式视觉

**文件：**
- 修改：`frontend/src/components/CustomerShell.tsx`
- 修改：`frontend/src/pages/ShopHome.tsx`
- 修改：`frontend/src/styles.css`

- [ ] **步骤 1：补充失败测试**

```tsx
expect(screen.getByRole('navigation', { name: '商城导航' })).toBeInTheDocument()
expect(screen.getByRole('heading', { name: '发现值得入手的科技好物' })).toBeInTheDocument()
```

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- --run src/pages/ShopHome.test.tsx`

预期：FAIL，现有导航没有语义名称，首屏标题仍为旧文案。

- [ ] **步骤 3：实现布局和样式**

为 `Menu` 添加 `aria-label="商城导航"`，保留文字品牌标识和购物车/订单入口。首页使用 `shop-hero__content`、`shop-category-nav`、`shop-product-grid`；桌面采用 `repeat(4, minmax(0, 1fr))`，在 `900px` 与 `640px` 降为三列和两列；图片保留 `aspect-ratio: 1` 与 `loading="lazy"`。

- [ ] **步骤 4：验证测试与构建**

运行：`npm --prefix frontend test -- --run src/pages/ShopHome.test.tsx; npm --prefix frontend run build`

预期：测试 PASS，Vite exit code 0。

- [ ] **步骤 5：提交**

运行：`git add frontend/src/components/CustomerShell.tsx frontend/src/pages/ShopHome.tsx frontend/src/styles.css frontend/src/pages/ShopHome.test.tsx; git commit -m "feat: 重构官方商城首页视觉"`

### 任务 3：商品详情购买区

**文件：**
- 创建：`frontend/src/pages/ProductDetail.test.tsx`
- 修改：`frontend/src/pages/ProductDetail.tsx`
- 修改：`frontend/src/styles.css`

- [ ] **步骤 1：编写失败测试并运行**

```tsx
expect(await screen.findByRole('button', { name: '加入购物车' })).toBeEnabled()
expect(screen.getByText('官方目录价格')).toBeInTheDocument()
```

运行：`npm --prefix frontend test -- --run src/pages/ProductDetail.test.tsx`

预期：FAIL，详情页没有“官方目录价格”说明。

- [ ] **步骤 2：实现两栏详情页**

将压缩单行组件展开为语义化 `main`、`section`、`h1`、`img` 和购买区。价格仅读取所选 `variant.price`，规格只用 `p.variants`，保留 `PUT /shop/cart/items/{variant}`；加载、404 与加购失败显示中文状态。

- [ ] **步骤 3：验证与提交**

运行：`npm --prefix frontend test -- --run src/pages/ProductDetail.test.tsx; npm --prefix frontend run build`

预期：测试 PASS，构建 exit code 0。

运行：`git add frontend/src/pages/ProductDetail.tsx frontend/src/pages/ProductDetail.test.tsx frontend/src/styles.css; git commit -m "feat: 优化商城商品详情购买区"`

### 任务 4：购物车、结算与订单统一布局

**文件：**
- 修改：`frontend/src/pages/Cart.tsx`
- 修改：`frontend/src/pages/Checkout.tsx`
- 修改：`frontend/src/pages/Orders.tsx`
- 修改：`frontend/src/styles.css`

- [ ] **步骤 1：编写失败测试并运行**

```tsx
expect(screen.getByRole('heading', { name: '购物袋' })).toBeInTheDocument()
expect(screen.getByText('模拟支付说明')).toBeInTheDocument()
```

运行：`npm --prefix frontend test -- --run src/pages/Cart.test.tsx src/pages/Checkout.test.tsx`

预期：FAIL，页面尚无统一标题与支付说明标签。

- [ ] **步骤 2：实现并验证**

添加 `storeflow-*` 类名，保留服务端 `total_amount`、现有幂等键、模拟支付 API、订单链接和状态。桌面端订单摘要位于右侧，`640px` 以下回到文档流且不遮挡提交按钮。

运行：`npm --prefix frontend test -- --run src/pages/Cart.test.tsx src/pages/Checkout.test.tsx; npm --prefix frontend run build`

预期：测试 PASS，构建 exit code 0。

- [ ] **步骤 3：提交**

运行：`git add frontend/src/pages/Cart.tsx frontend/src/pages/Checkout.tsx frontend/src/pages/Orders.tsx frontend/src/styles.css frontend/src/pages/Cart.test.tsx frontend/src/pages/Checkout.test.tsx; git commit -m "feat: 统一商城交易流程视觉"`

### 任务 5：回归与运行态验收

**文件：**
- 修改：`frontend/src/styles.css`（仅修复验收发现的商城样式问题）

- [ ] **步骤 1：运行前端与后端验证**

运行：`npm --prefix frontend run build; .venv\Scripts\python.exe -m pytest backend/tests/test_shop_api.py backend/tests/test_role_isolated_e2e.py -q`

预期：构建 exit code 0，所有后端商城相关测试 PASS。

- [ ] **步骤 2：运行态检查**

运行：`docker compose -f deploy/compose/docker-compose.yml up -d --build`，访问 `http://localhost`、`http://localhost:8001/healthz` 与 `http://localhost:8001/api/shop/products?page_size=1`。

预期：320px、768px、1440px 无横向滚动；健康接口为 `{"status":"ok"}`；商品接口返回真实目录。

- [ ] **步骤 3：提交验收修复（若有）**

运行：`git add frontend/src/styles.css; git commit -m "fix: 修正商城响应式展示"`
