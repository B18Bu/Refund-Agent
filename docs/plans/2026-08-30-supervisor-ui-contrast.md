# 主管端界面对比度与响应式优化实现计划

> **面向 AI 代理的工作者：** 在当前工作区内联执行，避免丢失未提交的前端现场改动。

**目标：** 修复主管导航徽标文字对比度，并改善现有页面在窄屏和键盘操作下的可用性，不改变业务功能。

**架构：** 保留 React、Ant Design、现有路由和请求逻辑；仅为现有组件增加语义类名/可访问属性，并在共享样式中补充颜色、焦点和响应式规则。

**技术栈：** React 18、TypeScript、Ant Design 5、CSS、Node 内置测试。

---

### 任务 1：建立 UI 回归契约

**文件：**
- 创建：`frontend/tests/ui-layout.test.mjs`

- [x] 测试主管徽标导航继承菜单前景色，且关键页面具备响应式类名。
- [x] 运行 `node --test frontend/tests/ui-layout.test.mjs`，确认因契约尚未实现而失败。

### 任务 2：最小化界面修复

**文件：**
- 修改：`frontend/src/components/AppShell.tsx`
- 修改：`frontend/src/pages/Dashboard.tsx`
- 修改：`frontend/src/pages/Login.tsx`
- 修改：`frontend/src/pages/TicketDetail.tsx`
- 修改：`frontend/src/pages/Screen.tsx`
- 修改：`frontend/src/components/ApprovePanel.tsx`
- 修改：`frontend/src/styles.css`

- [x] 为导航、应用头部、表格、详情、审批和大屏添加语义类名。
- [x] 让徽标文字继承菜单颜色，并增加清晰的选中、悬停、焦点状态。
- [x] 添加 768px/640px 响应式规则与表格横向滚动，不修改路由和事件处理。
- [x] 为登录字段添加可见标签，为可点击工单行增加键盘入口。

### 任务 3：验证

- [x] 运行 `node --test frontend/tests/ui-layout.test.mjs`，3 项全部通过。
- [x] 运行 `npm --prefix frontend run build`，TypeScript 与 Vite 构建成功。
- [x] 检查 `git diff`，确认仅包含计划内前端改动和本计划。
