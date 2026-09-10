# 智能客服推荐与人工答疑修复实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让拍照手机推荐只选择手机、完整展示商品信息与图片，并验证人工答疑入口可用。

**架构：** 后端在受限目录检索中加入确定性的商品类别过滤；会话证据只扩展现有受控商品字段。前端渲染第一条有效推荐的名称、说明、图片和详情按钮；客服会话仍复用既有 API 与 RBAC。

**技术栈：** FastAPI、SQLAlchemy、React、TypeScript、Vitest、Pytest、Docker Compose。

---

### 任务 1：限制手机推荐并扩充会话证据

**文件：**
- 修改：`backend/app/customer_assistant/service.py`
- 修改：`backend/app/customer_assistant/conversations.py`
- 测试：`backend/tests/test_customer_assistant_service.py`
- 测试：`backend/tests/test_customer_support_conversations.py`

- [ ] **步骤 1：编写失败的后端测试**

添加一个 `PHONE` 商品和一个文本更匹配的 `PERIPHERAL` 商品；断言 `CustomerAssistantService.reply(user, "推荐拍照手机", {})` 只返回手机来源。向会话断言增加 `description`、`image_url`、`category`。

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest backend/tests/test_customer_assistant_service.py backend/tests/test_customer_support_conversations.py -q`

预期：FAIL，外设会被命中或推荐证据缺少扩展字段。

- [ ] **步骤 3：实现最少后端代码**

在 `_search_catalog` 的现有激活商品查询中，仅当请求明确含“手机”时加入 `Product.category == "PHONE"`；在 `ConversationService.reply` 的已有 `products` 字典中加入安全的商品描述、图片 URL 与分类字段。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest backend/tests/test_customer_assistant_service.py backend/tests/test_customer_support_conversations.py -q`

预期：PASS。

### 任务 2：渲染推荐商品图片与说明

**文件：**
- 修改：`frontend/src/types/shop.ts`
- 修改：`frontend/src/pages/CustomerAssistant.tsx`
- 修改：`frontend/src/pages/CustomerAssistant.test.tsx`

- [ ] **步骤 1：编写失败的前端测试**

为推荐证据提供 `description` 与 `image_url`，断言名称、说明、图片和“查看商品信息”都出现，且名称与说明位于详情按钮之前。

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`

预期：FAIL，推荐图片或说明不存在。

- [ ] **步骤 3：实现最少前端代码**

扩展推荐证据类型，并在已有 `assistant-message__product` 中按名称、说明、图片、按钮顺序渲染。图片为空时使用 `/placeholder-product.svg`。

- [ ] **步骤 4：运行测试验证通过**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx src/pages/CustomerSupportChat.test.tsx`

预期：PASS。

### 任务 3：构建并核验运行镜像

**文件：** 无代码文件修改。

- [ ] **步骤 1：执行回归与构建**

运行：`python -m pytest backend/tests/test_customer_assistant_service.py backend/tests/test_customer_support_conversations.py -q` 和 `npm --prefix frontend run build`。

- [ ] **步骤 2：重建并启动容器**

运行：`docker compose --env-file .env -f deploy/compose/docker-compose.yml up -d --build`。

- [ ] **步骤 3：检查运行状态**

运行：`docker compose --env-file .env -f deploy/compose/docker-compose.yml ps` 与 `Invoke-WebRequest http://localhost/`。

预期：应用容器运行，HTTP 状态为 `200`。
