# 结算地址创建与淡蓝商城视觉实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 客户可在结算页创建并选择收货地址完成模拟下单，商城客户界面统一为淡蓝视觉。

**架构：** 前端复用既有 `/shop/addresses` 创建接口，在 `Checkout` 内维护地址列表与抽屉表单状态。样式只调整客户商城专用选择器，不改后端权限、订单或支付流程。

**技术栈：** React 18、TypeScript、Ant Design、Vitest、Testing Library、CSS。

---

### 任务 1：结算页地址创建交互

**文件：**

- 修改：`frontend/src/pages/Checkout.tsx`
- 修改：`frontend/src/pages/Checkout.test.tsx`

- [ ] **步骤 1：编写失败的测试**

在 `Checkout.test.tsx` 使用空地址响应和现有 Testing Library 的 `fireEvent`：点击“新建收货地址”，填入李四、13900000000、广东、深圳、南山、科技园，点击“保存地址”；断言 `client.post('/shop/addresses', ...)` 被调用且新地址单选卡被自动选中。

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- --run src/pages/Checkout.test.tsx`

预期：FAIL，找不到“新建收货地址”按钮。

- [ ] **步骤 3：编写最少实现代码**

在 `Checkout.tsx` 增加 `drawerOpen`、`savingAddress` 与 Ant Design `Form`；在地址标题旁加入“新建收货地址”按钮和 `Drawer`。表单必填项为 `recipient_name`、`phone`、`province`、`city`、`district`、`detail`，手机号校验为 `/^1\d{10}$/`。成功请求后把响应加入 `addresses`、设置 `address` 为响应 id、关闭抽屉并重置表单。

- [ ] **步骤 4：运行测试验证通过**

运行：`npm --prefix frontend test -- --run src/pages/Checkout.test.tsx`

预期：PASS，创建请求与自动选择断言均成立。

- [ ] **步骤 5：Commit**

运行：`git add frontend/src/pages/Checkout.tsx frontend/src/pages/Checkout.test.tsx`

运行：`git commit -m "feat: 支持结算页创建收货地址"`

### 任务 2：淡蓝商城视觉与结算布局

**文件：**

- 修改：`frontend/src/styles.css`

- [ ] **步骤 1：定义商城色彩变量**

在 `:root` 增加 `--shop-primary: #3c8edb`、`--shop-primary-strong: #2374bd`、`--shop-surface: #f4f9ff` 与 `--shop-border: #cfe3f7`。

- [ ] **步骤 2：替换商城区域颜色**

把商城头部、搜索按钮、主导航、主会场、服务面板、价格强调、地址卡片和按钮的红色或深灰主色替换为淡蓝变量；保留三栏门户、真实商品图片、服务入口和现有响应式断点。

- [ ] **步骤 3：运行构建验证**

运行：`npm --prefix frontend run build`

预期：exit code 0。

- [ ] **步骤 4：Commit**

运行：`git add frontend/src/styles.css`

运行：`git commit -m "style: 统一商城淡蓝色视觉"`

### 任务 3：回归验证与运行容器

**文件：** 无。

- [ ] **步骤 1：运行商城前端测试**

运行：`npm --prefix frontend test -- --run src/pages/Checkout.test.tsx src/pages/ShopHome.test.tsx src/components/CustomerShell.test.tsx`

预期：所有测试通过。

- [ ] **步骤 2：运行商城后端回归**

运行：`.venv\Scripts\python.exe -m pytest backend/tests/test_shop_api.py backend/tests/test_role_isolated_e2e.py -q`

预期：所有测试通过。

- [ ] **步骤 3：重建并验证 Docker 前端**

运行：`docker compose -f deploy/compose/docker-compose.yml up -d --build frontend`

运行：`curl.exe -fsS http://localhost`

预期：首页 HTML 返回 200，且容器处于 Up 状态。
