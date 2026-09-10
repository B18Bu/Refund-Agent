# 智能客服商品详情跳转实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让商品推荐回复仅展示一个“查看商品信息”按钮，并跳转至排序第一件推荐商品的详情页。

**架构：** 商品检索证据由 `CustomerAssistantService` 携带受控 `product_id`；`ConversationService` 按排序持久化商品证据。前端只从第一条有效商品证据提取正整数 ID，推荐消息以商城内部路由按钮替代客服文本与外部来源链接。

**技术栈：** FastAPI、SQLAlchemy、React 18、React Router 6、Ant Design、Vitest、pytest。

---

## 文件结构

- `backend/app/customer_assistant/service.py`：目录检索证据增加内部商品 ID。
- `backend/app/customer_assistant/conversations.py`：会话 JSON 证据保存推荐商品 ID 和来源地址。
- `backend/tests/test_customer_assistant_service.py`：验证服务证据的商品 ID。
- `backend/tests/test_customer_support_conversations.py`：验证会话证据结构。
- `frontend/src/types/shop.ts`：声明推荐商品证据类型。
- `frontend/src/pages/CustomerAssistant.tsx`：渲染唯一商品详情按钮并导航。
- `frontend/src/pages/CustomerAssistant.test.tsx`：验证按钮和跳转行为。

### 任务 1：后端商品证据契约

**文件：** `backend/app/customer_assistant/service.py`、`backend/tests/test_customer_assistant_service.py`

- [ ] **步骤 1：编写失败测试**

```python
assert result.sources[0].product_id == product_id
```

在 `test_reply_uses_masked_question_and_catalog_sources_for_recommendation` 中保存 `_catalog_chunk` 的返回 ID 并断言首条来源带该 ID。

- [ ] **步骤 2：运行测试验证失败**

运行：`& '.venv\Scripts\python.exe' -m pytest backend/tests/test_customer_assistant_service.py::test_reply_uses_masked_question_and_catalog_sources_for_recommendation -q`

预期：FAIL，`CatalogEvidence` 没有 `product_id` 属性。

- [ ] **步骤 3：编写最少实现代码**

```python
@dataclass(frozen=True)
class CatalogEvidence:
    product_id: int
    source_url: str
    crawled_at: str | None
```

构造证据时填充 `chunk.product_id`，不改变检索排序或来源 URL。

- [ ] **步骤 4：运行测试验证通过**

运行：`& '.venv\Scripts\python.exe' -m pytest backend/tests/test_customer_assistant_service.py -q`

预期：PASS。

### 任务 2：会话推荐证据映射

**文件：** `backend/app/customer_assistant/conversations.py`、`backend/tests/test_customer_support_conversations.py`

- [ ] **步骤 1：编写失败测试**

```python
assert messages[1].evidence == {
    "products": [{"product_id": product.id, "source_url": "https://example.test/x100"}]
}
```

- [ ] **步骤 2：运行测试验证失败**

运行：`& '.venv\Scripts\python.exe' -m pytest backend/tests/test_customer_support_conversations.py::test_conversation_persists_masked_customer_and_assistant_turns -q`

预期：FAIL，当前证据仅有 `sources` URL 数组。

- [ ] **步骤 3：编写最少实现代码**

```python
evidence = {
    "products": [
        {"product_id": source.product_id, "source_url": source.source_url}
        for source in result.sources
    ]
}
```

仅在目录咨询分支写入该结构；订单、售后和人工处理分支维持既有证据。

- [ ] **步骤 4：运行测试验证通过**

运行：`& '.venv\Scripts\python.exe' -m pytest backend/tests/test_customer_support_conversations.py backend/tests/test_customer_assistant_service.py -q`

预期：PASS。

### 任务 3：前端唯一商品详情动作

**文件：** `frontend/src/types/shop.ts`、`frontend/src/pages/CustomerAssistant.tsx`、`frontend/src/pages/CustomerAssistant.test.tsx`

- [ ] **步骤 1：编写失败测试**

```tsx
expect(await screen.findByRole('button', { name: '查看商品信息' })).toBeInTheDocument()
expect(screen.queryByText('推荐商品文字')).not.toBeInTheDocument()
fireEvent.click(screen.getByRole('button', { name: '查看商品信息' }))
expect(screen.getByTestId('product-detail-route')).toBeInTheDocument()
```

模拟 `evidence.products: [{ product_id: 7, source_url: 'https://example.test/7' }]`，并为 `/shop/products/7` 配置测试路由。

- [ ] **步骤 2：运行测试验证失败**

运行：`npm --prefix frontend test -- CustomerAssistant.test.tsx --run`

预期：FAIL，当前组件仍展示回复文本与外部链接。

- [ ] **步骤 3：编写最少实现代码**

```tsx
const productId = item.evidence?.products?.find(
  (product) => Number.isInteger(product.product_id) && product.product_id > 0,
)?.product_id

{productId ? <Button type="primary" onClick={() => nav(`/shop/products/${productId}`)}>查看商品信息</Button> : <p>{item.content}</p>}
```

使用 `useNavigate`；有有效商品 ID 时不渲染助手文本或外部链接，客户和系统消息继续显示文本。

- [ ] **步骤 4：运行测试验证通过**

运行：`npm --prefix frontend test -- CustomerAssistant.test.tsx --run`

预期：PASS。

### 任务 4：跨层验证与提交

**文件：** 任务 1 至任务 3 的所有文件。

- [ ] **步骤 1：运行后端回归**

运行：`& '.venv\Scripts\python.exe' -m pytest backend/tests/test_customer_assistant_service.py backend/tests/test_customer_support_conversations.py backend/tests/test_customer_assistant_api.py -q`

预期：PASS。

- [ ] **步骤 2：运行前端回归与生产构建**

运行：`npm --prefix frontend test -- CustomerAssistant.test.tsx --run`

预期：PASS。

运行：`npm --prefix frontend run build`

预期：退出码 `0`。

- [ ] **步骤 3：检查变更并提交**

运行：`git diff --check`

预期：无差异空白错误。

```bash
git add backend/app/customer_assistant/service.py backend/app/customer_assistant/conversations.py backend/tests/test_customer_assistant_service.py backend/tests/test_customer_support_conversations.py frontend/src/types/shop.ts frontend/src/pages/CustomerAssistant.tsx frontend/src/pages/CustomerAssistant.test.tsx
git commit -m "feat: 客服推荐跳转商品详情"
```
