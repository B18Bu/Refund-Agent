# 消费者智能客服实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 建立消费者商品问答和主动推荐功能，使用商品知识、用户授权偏好和 DeepSeek 生成回答。

**架构：** 商品爬取结果进入独立消费者知识表；有效订单通过确定性规则形成偏好。对话仅在推荐意图下读取偏好，模型只能基于检索证据和确定性事实回答。

**技术栈：** FastAPI、SQLAlchemy、PostgreSQL pgvector、Redis、httpx、DeepSeek、React、TypeScript、Ant Design、pytest、Vitest。

---

## 文件结构

- `backend/migrations/20260907_add_customer_assistant.sql`：显式创建客服知识、偏好、忽略、会话和审计表；增加订单完成状态。
- `backend/app/customer_assistant/{models,schemas,catalog_index,preferences,service}.py`：隔离的数据模型、接口类型、索引、确定性偏好及对话编排。
- `backend/app/routers/customer_assistant.py`：仅消费者可访问的隐私设置与对话 API。
- `backend/app/{commerce_models,commerce_service,main}.py`、`backend/app/routers/shop.py`：受控订单完成状态和路由注册。
- `backend/app/worker/catalog_consumer.py`、`deploy/compose/docker-compose.yml`：商品索引及迁移/Worker 编排。
- `frontend/src/pages/{CustomerAssistant,PrivacyPreferences}.tsx`：消费者客服和隐私设置。
- `frontend/src/{App.tsx,components/CustomerShell.tsx,types/shop.ts,styles.css}`：路由、导航、类型和样式。
- `backend/tests/test_customer_assistant_*.py`、`frontend/src/pages/*.test.tsx`、`frontend/tests/customer-assistant-routing.test.mjs`：回归测试。

### 任务 1：有效订单和迁移

**文件：** `backend/migrations/20260907_add_customer_assistant.sql`、`backend/app/commerce_models.py`、`backend/app/commerce_service.py`、`backend/app/routers/shop.py`、`backend/tests/test_customer_assistant_models.py`。

- [ ] **步骤 1：编写失败测试**
```python
def test_only_completed_non_refunded_items_are_eligible(db_session):
    assert eligible_order_items(db_session, user_id) == [completed_normal_item]
```
- [ ] **步骤 2：运行失败测试**
运行：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_customer_assistant_models.py -q`
预期：FAIL，`eligible_order_items` 未定义。
- [ ] **步骤 3：最小实现**
```python
class OrderStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"

def eligible_order_items(session, user_id, since):
    return session.query(OrderItem).join(Order).filter(
        Order.user_id == user_id, Order.status == OrderStatus.COMPLETED,
        OrderItem.status == OrderItemStatus.NORMAL, Order.created_at >= since,
    ).all()
```
迁移以显式 SQL 建表；全额退款订单和部分退款明细必须从查询排除。
- [ ] **步骤 4：验证通过**
运行：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_customer_assistant_models.py backend/tests/test_shop_api.py -q`
预期：PASS。
- [ ] **步骤 5：Commit**：`git commit -m "feat: add completed orders for customer preferences"`

### 任务 2：授权偏好和永久忽略

**文件：** `backend/app/customer_assistant/models.py`、`backend/app/customer_assistant/preferences.py`、`backend/tests/test_customer_assistant_preferences.py`。

- [ ] **步骤 1：编写失败测试**
```python
def test_deleted_preference_is_not_rebuilt_until_restored(db_session):
    delete_preference(db_session, user_id, "brand")
    rebuild_preferences(db_session, user_id, now)
    assert preference_values(db_session, user_id, "brand") == []
```
- [ ] **步骤 2：运行失败测试**
运行：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_customer_assistant_preferences.py -q`
预期：FAIL，模型不存在。
- [ ] **步骤 3：最小实现**
```python
def rebuild_preferences(session, user_id, now):
    if not privacy_enabled(session, user_id): return []
    rows = eligible_order_items(session, user_id, now - timedelta(days=180))
    return persist_non_ignored_preferences(session, user_id, aggregate(rows), now)
```
保存授权、自动值、手动值、来源订单、置信度和忽略键；手动值优先。关闭授权清除画像及来源，不清除永久忽略项。
- [ ] **步骤 4：验证通过**
运行：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_customer_assistant_preferences.py -q`
预期：PASS，覆盖默认关闭、窗口、退款排除、手动优先、删除/恢复。
- [ ] **步骤 5：Commit**：`git commit -m "feat: add consented customer preference profiles"`

### 任务 3：隔离商品知识库

**文件：** `backend/app/customer_assistant/catalog_index.py`、`backend/app/worker/catalog_consumer.py`、`backend/tests/test_customer_assistant_catalog.py`。

- [ ] **步骤 1：编写失败测试**
```python
def test_index_excludes_unavailable_products_and_preserves_source(db_session):
    CustomerCatalogIndexer(db_session, FakeEmbedding()).index()
    assert only_chunk(db_session).source_url == "https://example.test/product"
```
- [ ] **步骤 2：运行失败测试**
运行：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_customer_assistant_catalog.py -q`
预期：FAIL，索引器不存在。
- [ ] **步骤 3：最小实现**
```python
for product in active_products(session):
    content, _ = DLP.mask(render_product_document(product))
    upsert_product_chunks(session, product, content, embedder.embed(split(content)))
```
新表记录商品 ID、来源 URL、抓取时间、哈希和向量；不得写入主管 `rag_documents`/`rag_chunks`。
- [ ] **步骤 4：验证通过**
运行：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_customer_assistant_catalog.py -q`
预期：PASS。
- [ ] **步骤 5：Commit**：`git commit -m "feat: index approved products for customer assistant"`

### 任务 4：消费者 API 和安全对话

**文件：** `backend/app/customer_assistant/{schemas,service}.py`、`backend/app/routers/customer_assistant.py`、`backend/app/main.py`、`backend/tests/test_customer_assistant_api.py`、`backend/tests/test_customer_assistant_service.py`。

- [ ] **步骤 1：编写失败测试**
```python
def test_non_recommendation_question_never_loads_preferences():
    service.reply(user, "这款手机支持双卡吗？")
    assert fake_preferences.read_calls == 0
```
- [ ] **步骤 2：运行失败测试**
运行：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_customer_assistant_api.py backend/tests/test_customer_assistant_service.py -q`
预期：FAIL，路由和服务不存在。
- [ ] **步骤 3：最小实现**
```python
def reply(self, user, message, context):
    safe, _ = DLP.mask(message)
    preferences = self.preferences.read(user.id) if classify_recommendation_intent(safe) else []
    evidence = self.catalog.search(safe, context.product_id, context.brand)
    return self.generator.generate(safe, evidence, preferences, self.facts(context))
```
路由限定 `Role.CUSTOMER` 和 JWT 用户 ID；隐私改动写审计。推荐意图使用确定性规则，DeepSeek 只接收脱敏问题、证据、允许偏好和确定性事实；无证据、模型失败或注入拦截时不得虚构。
- [ ] **步骤 4：验证通过**
运行：`.\\.venv\\Scripts\\python.exe -m pytest backend/tests/test_customer_assistant_api.py backend/tests/test_customer_assistant_service.py backend/tests/test_role_isolation.py -q`
预期：PASS，覆盖角色隔离、关闭授权、无证据、注入、超时和来源追溯。
- [ ] **步骤 5：Commit**：`git commit -m "feat: add grounded customer assistant APIs"`

### 任务 5：消费者前端、部署与端到端验证

**文件：** `frontend/src/pages/{CustomerAssistant,PrivacyPreferences}.tsx`、`frontend/src/App.tsx`、`frontend/src/components/CustomerShell.tsx`、`frontend/src/types/shop.ts`、`frontend/src/styles.css`、`frontend/src/pages/{CustomerAssistant,PrivacyPreferences}.test.tsx`、`frontend/tests/customer-assistant-routing.test.mjs`、`deploy/compose/docker-compose.yml`、`scripts/customer_assistant_e2e.py`。

- [ ] **步骤 1：编写失败测试**
```tsx
expect(await screen.findByText('推荐依据')).toBeInTheDocument()
```
- [ ] **步骤 2：运行失败测试**
运行：`npm --prefix frontend run test -- --run src/pages/CustomerAssistant.test.tsx src/pages/PrivacyPreferences.test.tsx`
预期：FAIL，页面不存在。
- [ ] **步骤 3：最小实现**
```tsx
<Route path="/shop/assistant" element={<CustomerAssistant />} />
<Route path="/shop/privacy" element={<PrivacyPreferences />} />
```
聊天页显示来源、抓取时间、推荐依据和降级状态；隐私页提供开关、编辑/删除偏好和恢复忽略项。Compose 显式运行迁移，端到端脚本验证授权、推荐门控、删除/恢复和角色隔离。
- [ ] **步骤 4：完整验证**
运行：`make check && make frontend-build && node --test frontend/tests/customer-assistant-routing.test.mjs && .\\.venv\\Scripts\\python.exe scripts/customer_assistant_e2e.py http://localhost:8001`
预期：全部通过。
- [ ] **步骤 5：Commit**：`git commit -m "feat: add customer assistant experience"`

## 自检结果

任务 1 至 5 覆盖商品知识隔离、授权、180 天有效订单、退款排除、永久忽略、手动优先、推荐意图门控、来源、降级和 RBAC。后续任务仅使用前序任务定义的接口；无未分配占位项。
