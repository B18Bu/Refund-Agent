# 主管政策依据 RAG 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 提供主管专用、可追溯来源的本地政策检索，不改变确定性退赔决策。

**架构：** PostgreSQL + pgvector 保存白名单文档 Chunk 与 512 维向量；独立 embedding 服务运行本地 `D:\\作业\\model\\bge-small-zh-v1.5`。RAG API 只输出原文片段和来源，故障返回 `unavailable`，不影响审批。

**技术栈：** FastAPI、SQLAlchemy、PostgreSQL + pgvector、sentence-transformers、React、Docker Compose、pytest。

---

## 文件结构

- 创建 `backend/app/rag/`：模型、文档索引、embedding、检索、查询编排和 API 类型。
- 创建 `backend/rag_embedding_service.py`：内网 `/healthz`、`/embed` 服务。
- 创建 RAG SQL 迁移、知识路由和后端 RAG 测试。
- 修改配置、模型注册、主应用、依赖与 Compose。
- 创建 `frontend/src/components/KnowledgeEvidence.tsx`，修改主管工单、评测页面、样式和 UI 测试。

### 任务 1：显式迁移与数据模型

**文件：** 创建 `backend/migrations/20260906_add_rag_knowledge.sql`、`backend/app/rag/models.py`、`backend/tests/test_rag_models.py`；修改 `backend/app/models.py`、`backend/app/main.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_rag_schema_uses_pgvector_migration():
    from app.rag.models import RagDocument, RagChunk, RagQueryLog
    assert "create extension if not exists vector" in MIGRATION.read_text().lower()
    assert {RagDocument.__tablename__, RagChunk.__tablename__, RagQueryLog.__tablename__} == {"rag_documents", "rag_chunks", "rag_query_logs"}
```

- [ ] **步骤 2：验证红灯**

运行：`.\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_rag_models.py`

预期：FAIL，`app.rag.models` 不存在。

- [ ] **步骤 3：最少实现**

迁移创建 `vector` 扩展及 `rag_documents`、`rag_chunks`、`rag_query_logs`。Chunk 表的向量维度为 512；表保存来源、哈希、版本、访问范围、DLP 查询摘要和命中文档 ID。`init_db()` 排除三个 RAG 表，禁止隐式建表。

- [ ] **步骤 4：验证绿灯并提交**

运行：`.\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_rag_models.py backend/tests/test_evaluation_api.py`

预期：PASS。

提交：`git add backend/migrations/20260906_add_rag_knowledge.sql backend/app/rag/models.py backend/app/models.py backend/app/main.py backend/tests/test_rag_models.py && git commit -m "feat: add explicit RAG schema"`

### 任务 2：本地 embedding 和文档索引

**文件：** 创建 `backend/rag_embedding_service.py`、`backend/app/rag/embeddings.py`、`documents.py`、`indexer.py`、相关测试；修改 `backend/app/config.py`、`backend/requirements.txt`。

- [ ] **步骤 1：编写失败测试**

```python
def test_embedding_client_rejects_wrong_dimension(httpx_mock):
    client = EmbeddingClient("http://embedding:8080", dimension=512)
    httpx_mock.post("http://embedding:8080/embed", json={"vectors": [[0.1]]})
    with pytest.raises(EmbeddingUnavailable): client.embed(["退款政策"])

def test_indexer_masks_sensitive_text_and_is_idempotent():
    assert "13800000000" not in indexed_chunk.content
    assert second_run.created_chunks == 0
```

- [ ] **步骤 2：验证红灯**

运行：`.\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_rag_embeddings.py backend/tests/test_rag_documents.py`

预期：FAIL，客户端与索引器不存在。

- [ ] **步骤 3：最少实现**

索引器只读取规格中的白名单，文本先经 DLP 掩码后切分、向量化和按哈希幂等写入。模型固定为本地 `D:\\作业\\model\\bge-small-zh-v1.5`，输出 512 维向量；模型目录缺失时健康检查失败，禁止下载。入口为 `python -m app.rag.indexer`。

- [ ] **步骤 4：验证绿灯并提交**

运行：`.\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_rag_embeddings.py backend/tests/test_rag_documents.py`

预期：PASS。

提交：`git add backend/rag_embedding_service.py backend/app/rag backend/app/config.py backend/requirements.txt backend/tests/test_rag_embeddings.py backend/tests/test_rag_documents.py && git commit -m "feat: add local RAG indexing"`

### 任务 3：主管检索 API 与安全降级

**文件：** 创建 `backend/app/rag/schemas.py`、`retriever.py`、`service.py`、`backend/app/routers/knowledge.py`、检索和 API 测试；修改 `backend/app/main.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_customer_service_cannot_read_knowledge(client, cs_token):
    assert client.get("/api/tickets/1/knowledge", headers=auth(cs_token)).status_code == 403
def test_embedding_failure_returns_unavailable_without_decision_change(client, sv_token, ticket):
    assert client.get(f"/api/tickets/{ticket.id}/knowledge", headers=auth(sv_token)).json()["status"] == "unavailable"
    assert ticket.decision == Decision.PENDING
```

- [ ] **步骤 2：验证红灯**

运行：`.\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_rag_retriever.py backend/tests/test_rag_api.py`

预期：FAIL，知识路由不存在。

- [ ] **步骤 3：最少实现**

实现 `GET /api/tickets/{ticket_id}/knowledge` 与评测知识接口，均用 `require_role(Role.SV)`。参数化 pgvector 查询最多返回 5 条；低相似度返回 `empty`。响应包含 `available`、`query_id`、`status`、`results`，结果包含原文、来源、章节、版本和相似度。故障统一为 `unavailable`，不得改动工单。

- [ ] **步骤 4：验证绿灯并提交**

运行：`.\\.venv\\Scripts\\python.exe -m pytest -q backend/tests/test_rag_retriever.py backend/tests/test_rag_api.py backend/tests/test_security_e2e.py`

预期：PASS。

提交：`git add backend/app/rag backend/app/routers/knowledge.py backend/app/main.py backend/tests/test_rag_retriever.py backend/tests/test_rag_api.py && git commit -m "feat: add supervisor knowledge retrieval"`

### 任务 4：主管界面和部署门禁

**文件：** 创建 `frontend/src/components/KnowledgeEvidence.tsx`；修改工单、评测页面、样式、UI 测试、Compose。

- [ ] **步骤 1：编写失败测试**

```javascript
test('主管页面展示可追溯政策依据且不替代审批', () => {
  assert.match(read('components/KnowledgeEvidence.tsx'), /来源|版本|相似度/)
  assert.match(read('pages/TicketDetail.tsx'), /KnowledgeEvidence/)
  assert.match(compose, /rag-embedding:|rag-migrate:/)
})
```

- [ ] **步骤 2：验证红灯**

运行：`node --test frontend/tests/evaluation-ui.test.mjs frontend/tests/deployment-init.test.mjs`

预期：FAIL，组件及 Compose RAG 服务不存在。

- [ ] **步骤 3：最少实现**

组件展示加载、`empty`、`unavailable` 与结果状态，仅在主管页请求；不得产生审批建议。Compose 使用 pgvector PostgreSQL、显式 `rag-migrate` 和有健康检查的 `rag-embedding`；API 等待迁移而不等待 embedding，索引始终独立显式运行。

- [ ] **步骤 4：验证绿灯并提交**

运行：`node --test frontend/tests/evaluation-ui.test.mjs frontend/tests/deployment-init.test.mjs; docker compose -f deploy/compose/docker-compose.yml config --quiet; npm --prefix frontend run build`

预期：全部 PASS。

提交：`git add frontend/src/components/KnowledgeEvidence.tsx frontend/src/pages/TicketDetail.tsx frontend/src/pages/Evaluations.tsx frontend/src/styles.css frontend/tests deploy/compose/docker-compose.yml && git commit -m "feat: deploy supervisor RAG evidence"`

## 自检结果

规格中的主管 RBAC、白名单、512 维 pgvector、本地 `D:\\作业\\model\\bge-small-zh-v1.5`、引用输出、DLP、审计、故障降级和部署门禁均有对应任务。计划不引入历史工单、外部知识源、LLM 总结或对退赔决策的写入。
