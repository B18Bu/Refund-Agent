# 顾客智能客服历史会话抽屉实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 以侧边抽屉展示顾客历史会话，并支持不破坏审计证据的持久化隐藏。

**架构：** 新增顾客-会话隐藏关系表；列表查询排除当前用户的隐藏关系；抽屉只消费已有会话 API 和新的幂等隐藏端点。

**技术栈：** FastAPI、SQLAlchemy、PostgreSQL、React、Ant Design、Vitest、Pytest。

---

### 任务 1：持久化隐藏关系与归属接口

**文件：**
- 创建：`backend/migrations/20260910_add_customer_hidden_conversations.sql`
- 修改：`backend/app/customer_assistant/models.py`
- 修改：`backend/app/customer_assistant/conversations.py`
- 修改：`backend/app/routers/customer_assistant.py`
- 测试：`backend/tests/test_customer_support_api.py`

- [ ] **步骤 1：编写失败测试**

创建顾客 A、顾客 B 和各自会话；顾客 A 删除自己的会话两次均返回成功，列表不再含该会话，顾客 B 不能删除 A 的会话且返回 `404`。

- [ ] **步骤 2：运行失败测试**

运行：`python -m pytest backend/tests/test_customer_support_api.py -q`

预期：FAIL，因为删除端点不存在。

- [ ] **步骤 3：实现最少代码**

迁移创建：

```sql
CREATE TABLE customer_hidden_conversations (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  conversation_id INTEGER NOT NULL REFERENCES customer_support_conversations(id),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT uq_customer_hidden_conversations UNIQUE (user_id, conversation_id)
);
```

`hide_conversation` 先验证会话归属，再用唯一约束实现幂等写入；`list_conversations` 排除当前用户隐藏关系；新增 `DELETE /conversations/{conversation_id}`。

- [ ] **步骤 4：运行通过测试**

运行：`python -m pytest backend/tests/test_customer_support_api.py -q`

预期：PASS。

### 任务 2：抽屉交互与十字摘要

**文件：**
- 修改：`frontend/src/pages/CustomerAssistant.tsx`
- 修改：`frontend/src/styles.css`
- 测试：`frontend/src/pages/CustomerAssistant.test.tsx`

- [ ] **步骤 1：编写失败测试**

Mock 长摘要，断言抽屉显示前 10 个字符加 `...`；点击删除图标打开确认框，确认后调用 `DELETE /customer-assistant/conversations/6` 并从抽屉移除项目。

- [ ] **步骤 2：运行失败测试**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`

预期：FAIL，因为不存在删除按钮与确认交互。

- [ ] **步骤 3：实现最少代码**

使用 Ant Design `Drawer` 和 `Popconfirm` 替换内嵌 `aside`；定义 `summarize(text) => text.length > 10 ? text.slice(0, 10) + '...' : text`。每项为无卡片分隔行，删除点击停止事件传播。

- [ ] **步骤 4：运行通过测试**

运行：`npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`

预期：PASS。

### 任务 3：构建、迁移与运行态验证

**文件：** 无新增产品代码。

- [ ] **步骤 1：相关回归**

运行：`python -m pytest backend/tests/test_customer_support_api.py backend/tests/test_customer_support_conversations.py -q` 与 `npm --prefix frontend test -- --run src/pages/CustomerAssistant.test.tsx`。

- [ ] **步骤 2：生产构建与容器验证**

运行：`npm --prefix frontend run build`，`docker compose --env-file .env -f deploy/compose/docker-compose.yml up -d --build`，`Invoke-WebRequest -UseBasicParsing http://localhost/`。

预期：全部测试和构建通过，HTTP `200`。
