# 品牌优选商城高效率交易型改版实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将消费者商城首页改为搜索、分类与商品浏览优先的高效率交易界面，同时保留悬浮多轮智能客服。

**架构：** `CustomerShell` 收束为品牌、搜索、订单和购物车加一层主导航。`ShopHome` 负责首屏主会场、可点击的分类快捷入口、服务说明带、筛选与商品网格；继续调用现有 `/shop/products` 与 `/shop/brands` 接口。`styles.css` 只重写商城相关选择器，沿用现有 `--shop-*` 语义变量和客服浮窗层级。

**技术栈：** React 18、React Router 6、Ant Design、Vitest、Testing Library、Vite、Docker Compose。

---

## 文件结构

- 修改：`frontend/src/components/CustomerShell.tsx`：移除重复工具栏，保留紧凑商城头部与悬浮客服挂载点。
- 修改：`frontend/src/components/CustomerShell.test.tsx`：验证单层导航、搜索和悬浮客服入口。
- 修改：`frontend/src/pages/ShopHome.tsx`：将三栏首屏改成单主会场、分类快捷入口和服务说明带。
- 修改：`frontend/src/pages/ShopHome.test.tsx`：验证目录驱动分类、首屏结构与服务承诺。
- 修改：`frontend/src/styles.css`：定义商城高效率交易型布局、蓝色操作语义、商品网格和 375px 响应式规则。

### 任务 1：锁定新的商城信息架构

**文件：**
- 修改：`frontend/src/pages/ShopHome.test.tsx`
- 修改：`frontend/src/components/CustomerShell.test.tsx`

- [ ] **步骤 1：编写首页结构失败测试**

将 `ShopHome` 测试替换为以下断言，保持 `client.get` mock 与现有 `headset`、`phone` 目录数据：

```tsx
expect(await screen.findByRole('region', { name: '商城主会场' })).toBeInTheDocument()
expect(screen.getByRole('navigation', { name: '商品快捷分类' })).toBeInTheDocument()
expect(screen.getByRole('button', { name: '耳机' })).toBeInTheDocument()
expect(screen.getByRole('region', { name: '商城服务承诺' })).toBeInTheDocument()
expect(screen.queryByRole('complementary', { name: '用户服务' })).not.toBeInTheDocument()
expect(screen.queryByRole('navigation', { name: '全部商品分类' })).not.toBeInTheDocument()
```

- [ ] **步骤 2：运行首页测试确认失败**

运行：

```powershell
npm --prefix frontend test -- --run src/pages/ShopHome.test.tsx
```

预期：失败，原因是当前页面仍存在 `全部商品分类` 左栏和 `用户服务` 右栏。

- [ ] **步骤 3：编写商城壳层失败测试**

将壳层测试名称改为“为商城提供紧凑导航、搜索和悬浮客服”，并添加：

```tsx
expect(screen.queryByRole('navigation', { name: '商城工具栏' })).not.toBeInTheDocument()
expect(screen.getByRole('search', { name: '搜索商城商品' })).toBeInTheDocument()
expect(screen.getByRole('navigation', { name: '商城主导航' })).toBeInTheDocument()
expect(screen.getByRole('button', { name: '打开智能客服' })).toBeInTheDocument()
```

- [ ] **步骤 4：运行壳层测试确认失败**

运行：

```powershell
npm --prefix frontend test -- --run src/components/CustomerShell.test.tsx
```

预期：失败，原因是当前仍渲染 `商城工具栏`。

- [ ] **步骤 5：提交测试契约**

```powershell
git add frontend/src/pages/ShopHome.test.tsx frontend/src/components/CustomerShell.test.tsx
git commit -m "test: 约束商城高效率交易布局"
```

### 任务 2：实现搜索优先的商城头部与首页结构

**文件：**
- 修改：`frontend/src/components/CustomerShell.tsx`
- 修改：`frontend/src/pages/ShopHome.tsx`

- [ ] **步骤 1：收束商城头部为两层**

删除 `CustomerShell` 中的 `customer-utility-nav`，保留 `customer-search-row` 与 `customer-main-nav`。`customer-search-row` 必须继续使用现有 `search` 函数和以下可访问名称：

```tsx
<form className="customer-search" role="search" aria-label="搜索商城商品" onSubmit={search}>
  <Input aria-label="搜索商城商品" placeholder="搜索商品、型号或配件" ... />
  <Button htmlType="submit" type="primary">搜索</Button>
</form>
```

保留订单、购物车和退出登录功能；`<CustomerAssistant />` 保持在 `Layout` 内，不能移动到导航或首页内容中。

- [ ] **步骤 2：替换三栏首屏为主会场与快捷分类**

在 `ShopHome` 中移除 `shop-portal`、`shop-category-menu` 和 `shop-service-panel` 节点。新增以下结构，并继续使用现有 `categories` 与 `setKeyword`：

```tsx
<section className="shop-hero" aria-label="商城主会场">
  <div className="shop-hero__content">
    <p className="shop-eyebrow">官方目录，每日更新</p>
    <h1>快速找到适合你的设备</h1>
    <p>商品价格、规格与可售状态均来自品牌官方目录。</p>
    <Link className="shop-hero__action" to={featuredProduct ? `/shop/products/${featuredProduct.id}` : '/shop'}>
      {featuredProduct ? '查看精选商品' : '浏览官方目录'}
    </Link>
  </div>
  {featuredProduct?.image_url && <img className="shop-hero__image" src={featuredProduct.image_url} alt={`${featuredProduct.brand} ${featuredProduct.name}`} />}
</section>
<nav className="shop-category-nav" aria-label="商品快捷分类">
  <span>快速分类</span>
  {categories.map((item) => <button key={item.label} type="button" onClick={() => setKeyword(item.keywords[0])}>{item.label}</button>)}
</nav>
<section className="shop-service-strip" aria-label="商城服务承诺">...</section>
```

服务说明带内保持“官方来源、规格透明、订单可查、售后承接”四项文本，不复用旧右侧服务卡。

- [ ] **步骤 3：保持确定性筛选与商品导航**

保留 `params` 的 `keyword`、`brand`、`min_price`、`max_price` 计算逻辑，保留 `load`、空态、错误态和 `Link to={`/shop/products/${product.id}`}`。不要把筛选路由、价格计算或产品卡的可用规格筛选交给模型处理。

- [ ] **步骤 4：运行定向测试确认通过**

运行：

```powershell
npm --prefix frontend test -- --run src/pages/ShopHome.test.tsx src/components/CustomerShell.test.tsx src/pages/CustomerAssistant.test.tsx
```

预期：3 个测试文件全部通过；客服测试仍验证悬浮入口、默认收起和消息角色。

- [ ] **步骤 5：提交结构实现**

```powershell
git add frontend/src/components/CustomerShell.tsx frontend/src/pages/ShopHome.tsx frontend/src/pages/ShopHome.test.tsx frontend/src/components/CustomerShell.test.tsx
git commit -m "feat: 优化商城搜索与商品发现布局"
```

### 任务 3：实现高效率交易型视觉与响应式行为

**文件：**
- 修改：`frontend/src/styles.css`

- [ ] **步骤 1：定义商城语义颜色与紧凑头部样式**

在现有 `--shop-*` 变量旁补充商城页面使用的语义变量，不改变后台页面变量：

```css
--shop-page: #f4f6fa;
--shop-ink: #172033;
--shop-muted: #64748b;
--shop-line: #dbe5ef;
--shop-action: #2f7fc5;
--shop-action-strong: #216eae;
```

将 `customer-search-row` 调整为品牌、可伸缩搜索、操作入口三列，最小高度不超过 80px。删除旧工具栏选择器和红色覆盖规则，搜索框、主按钮、已选标签与悬浮客服统一使用 `--shop-action`。

- [ ] **步骤 2：实现首屏、分类、筛选与商品网格**

按以下尺寸约束编写商城样式：

```css
.shop-home { max-width: 1248px; padding-block: 24px 64px; }
.shop-hero { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, .8fr); min-height: 320px; }
.shop-category-nav { display: flex; gap: 8px; overflow-x: auto; padding-block: 18px; }
.shop-filters { grid-template-columns: minmax(180px, 1fr) 160px auto; }
.shop-products { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
```

主会场背景使用白色或浅蓝实色分区，不使用渐变、装饰圆形或大面积高饱和色。商品卡保持 0-8px 圆角和固定 `aspect-ratio` 商品图；悬浮客服保持 `z-index: 1000`，在筛选与商品内容之上。

- [ ] **步骤 3：实现 900px 与 640px 响应式规则**

在 900px 下将商品网格改为三列、隐藏非必要头部操作；在 640px 下将头部搜索行压缩为品牌加搜索、商品网格改为两列、筛选改为单列加搜索按钮。浮窗继续使用：

```css
@media (max-width: 720px) {
  .assistant-launcher { right: 16px; bottom: 16px; }
  .assistant-float { right: 16px; bottom: 84px; width: min(440px, calc(100vw - 32px)); }
}
```

所有链接、价格、商品标题允许换行或省略但不溢出；焦点状态继续使用 `--color-focus`；`prefers-reduced-motion` 下取消商品卡位移动画。

- [ ] **步骤 4：运行构建与视觉回归检查**

运行：

```powershell
npm --prefix frontend run build
```

预期：`✓ built`；允许既有 chunk 大小告警，但不得有 TypeScript 或 Vite 错误。随后在 1440px、768px、375px 宽度查看 `/shop`，确认首屏不存在三栏面板，右下角客服可见且不遮挡筛选输入。

- [ ] **步骤 5：提交样式实现**

```powershell
git add frontend/src/styles.css
git commit -m "style: 调整商城高效率交易视觉"
```

### 任务 4：统一容器验收

**文件：**
- 不修改文件。

- [ ] **步骤 1：重建唯一应用容器**

运行：

```powershell
docker compose -f deploy/compose/docker-compose.yml up -d --build app
```

预期：只运行 `compose-app-1` 作为应用容器；不得执行 `docker compose down -v`。

- [ ] **步骤 2：验证健康与已部署前端资源**

运行：

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost/healthz
docker exec compose-app-1 sh -lc 'grep -R -q "打开智能客服" /usr/share/nginx/html/assets && echo floating_assistant=present'
Invoke-WebRequest -UseBasicParsing http://localhost/shop
```

预期：健康响应为 `{"status":"ok"}`，`floating_assistant=present`，商城页面返回 `200`。

- [ ] **步骤 3：提交验收前变更**

```powershell
git status --short
```

预期：只显示本计划范围内尚未提交的文件；不得覆盖或还原用户已有改动。
