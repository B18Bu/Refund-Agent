# 任务五：目录 Worker 与电商端到端验收实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 以最小权限 Docker Worker 启动与周期抓取 vivo、OPPO，只有完整真实快照通过门槛才发布商城目录。

**架构：** 抓取服务返回内存 DTO 快照；目录模块使用 `asyncio.gather(..., return_exceptions=True)` 聚合两品牌、校验后单事务发布；Worker 不进入 API 请求链路。

**技术栈：** Python 3.11、FastAPI、SQLAlchemy、httpx、pytest、Docker Compose、Vite。

---

## 文件清单与职责

- 修改 `backend/app/scraping/service.py`：新增不写库的受控快照入口。
- 修改 `backend/app/catalog_initialization.py`：编排双品牌快照、原子发布与失败回退。
- 创建 `backend/app/worker/catalog_consumer.py`：启动即运行、周期刷新和会话关闭。
- 修改 `backend/app/config.py`、`deploy/compose/docker-compose.yml`：刷新周期和无卷挂载 Worker。
- 修改 `backend/tests/test_catalog_initialization.py`、`backend/tests/test_scraping.py`：快照、门禁、回退和 Worker 测试。
- 创建 `backend/tests/test_role_isolated_e2e.py`，修改 `scripts/commerce_e2e.py`：角色与目录 HTTP 验收。

### 任务 1：提取不写库的固定来源快照

**文件：** 修改 `backend/app/scraping/service.py`；测试 `backend/tests/test_scraping.py`。

- [ ] **步骤 1：编写失败测试**

```python
@pytest.mark.asyncio
async def test_fetch_snapshot_uses_fixed_source_and_does_not_write_products(db_session, monkeypatch):
    service = ScrapeService(db_session)
    monkeypatch.setattr(service, "_request_source", AsyncMock(return_value='{"products": []}'))
    assert await service.fetch_snapshot("vivo") == []
    assert db_session.query(Product).count() == 0
```

- [ ] **步骤 2：运行失败测试**

运行 `.venv\\Scripts\\python.exe -m pytest backend/tests/test_scraping.py::test_fetch_snapshot_uses_fixed_source_and_does_not_write_products -q`。预期 FAIL：`fetch_snapshot` 不存在。

- [ ] **步骤 3：编写最少实现代码**

```python
async def fetch_snapshot(self, source_site: str) -> list[ProductDTO]:
    if source_site not in ADAPTERS:
        raise ValueError(f"不支持的商品来源: {source_site}")
    text = await self._request_source(source_site)
    return ADAPTERS[source_site]().parse(text, SOURCE_URLS[source_site])
```

将既有 HTTP 调用提为 `_request_source`；保留 `scrape_source` 的 ScrapeRun 与写库语义。

- [ ] **步骤 4：验证并提交**

运行 `.venv\\Scripts\\python.exe -m pytest backend/tests/test_scraping.py -q`，预期 PASS。

```bash
git add backend/app/scraping/service.py backend/tests/test_scraping.py && git commit -m "feat: 提取受控商品抓取快照"
```

### 任务 2：原子发布完整目录与失败回退

**文件：** 修改 `backend/app/catalog_initialization.py`；测试 `backend/tests/test_catalog_initialization.py`。

- [ ] **步骤 1：编写失败测试**

```python
@pytest.mark.asyncio
async def test_first_run_with_one_failed_brand_publishes_no_products(db_session, monkeypatch):
    monkeypatch.setattr(ScrapeService, "fetch_snapshot",
                        AsyncMock(side_effect=[_snapshot()["vivo"], RuntimeError("oppo down")]))
    result = await run_catalog_initialization(db_session)
    assert result.status == CatalogStatus.INITIALIZATION_FAILED
    assert db_session.query(Product).count() == 0
```

另写成功目录后单品牌失败的用例，断言 `READY`、`used_cached_catalog=True` 与原商品保留。

- [ ] **步骤 2：运行失败测试**

运行 `.venv\\Scripts\\python.exe -m pytest backend/tests/test_catalog_initialization.py -q`。预期 FAIL：`run_catalog_initialization` 不存在。

- [ ] **步骤 3：编写最少实现代码**

```python
CATALOG_SOURCES = ("vivo", "oppo")
async def run_catalog_initialization(db: Session) -> CatalogResult:
    results = await asyncio.gather(
        *(ScrapeService(db).fetch_snapshot(source) for source in CATALOG_SOURCES),
        return_exceptions=True,
    )
    if any(isinstance(value, Exception) for value in results):
        return record_catalog_failure(db, "SOURCE_FETCH_FAILED")
    return refresh_catalog(db, dict(zip(CATALOG_SOURCES, results)))
```

`publish_successful_catalog` 在一个事务中 upsert，异常 rollback；首次失败写 `INITIALIZATION_FAILED`，已有 READY 时保持目录并记录错误。

- [ ] **步骤 4：验证并提交**

运行 `.venv\\Scripts\\python.exe -m pytest backend/tests/test_catalog_initialization.py backend/tests/test_scraping.py -q`，预期 PASS。

```bash
git add backend/app/catalog_initialization.py backend/tests/test_catalog_initialization.py && git commit -m "feat: 原子发布商品目录快照"
```

### 任务 3：新增 Worker 与最小权限 Compose 服务

**文件：** 创建 `backend/app/worker/catalog_consumer.py`；修改 `backend/app/config.py`、`deploy/compose/docker-compose.yml`；测试 `backend/tests/test_catalog_initialization.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_catalog_refresh_interval_defaults_to_daily():
    assert Settings().CATALOG_REFRESH_SECONDS == 86400
```

用 mock 的 `SessionLocal`、`run_catalog_initialization`、`time.sleep` 断言：第一次 sleep 前运行初始化，且每轮 finally 关闭会话。

- [ ] **步骤 2：运行失败测试**

运行 `.venv\\Scripts\\python.exe -m pytest backend/tests/test_catalog_initialization.py -q`。预期 FAIL：配置字段与 Worker 模块不存在。

- [ ] **步骤 3：编写最少实现代码**

```python
def run_once() -> None:
    db = SessionLocal()
    try:
        asyncio.run(run_catalog_initialization(db))
    finally:
        db.close()
```

`run_forever` 每次 `run_once` 后 sleep `settings.CATALOG_REFRESH_SECONDS`。Compose 使用 `python -m app.worker.catalog_consumer`，只配数据库、Redis、抓取与刷新变量，且没有 `volumes`。

- [ ] **步骤 4：验证并提交**

运行 `.venv\\Scripts\\python.exe -m pytest backend/tests/test_catalog_initialization.py -q; docker compose -f deploy/compose/docker-compose.yml config`，预期 PASS 且 `catalog-worker` 无卷挂载。

```bash
git add backend/app/worker/catalog_consumer.py backend/app/config.py deploy/compose/docker-compose.yml backend/tests/test_catalog_initialization.py && git commit -m "feat: 增加目录初始化 Worker"
```

### 任务 4：目录门禁与角色电商 E2E

**文件：** 创建 `backend/tests/test_role_isolated_e2e.py`；修改 `scripts/commerce_e2e.py`。

- [ ] **步骤 1：编写失败测试**

```python
def test_catalog_not_ready_rejects_browse_and_customer_cart(client, customer_headers):
    assert client.get("/api/shop/products").status_code == 503
    assert client.put("/api/shop/cart/items/1", json={"quantity": 1},
                      headers=customer_headers).status_code == 409
```

同文件复用现有夹具，断言 CS/SV 商城写操作为 403、人工退款第二次审批为 409。

- [ ] **步骤 2：运行失败测试**

运行 `.venv\\Scripts\\python.exe -m pytest backend/tests/test_role_isolated_e2e.py -q`。预期 FAIL：测试文件不存在。

- [ ] **步骤 3：编写最少实现代码**

```python
except HTTPError as exc:
    if exc.code == 503:
        raise RuntimeError("商品目录未就绪：目录 Worker 未通过真实抓取门槛") from exc
    raise
```

`commerce_e2e.py` 捕获目录 503、使用演示账号登录后验证浏览；不伪造商品，不绕过凭证或角色校验。

- [ ] **步骤 4：验证并提交**

运行 `.venv\\Scripts\\python.exe -m pytest backend/tests/test_role_isolated_e2e.py backend/tests/test_role_isolation.py -q`，预期 PASS。

```bash
git add backend/tests/test_role_isolated_e2e.py scripts/commerce_e2e.py && git commit -m "test: 覆盖目录 Worker 电商验收"
```

### 任务 5：回归与 Docker 验收

- [ ] **步骤 1：运行回归**

运行 `.venv\\Scripts\\python.exe -m pytest backend/tests -q; npm --prefix frontend run build`。预期测试与 Vite 构建通过。

- [ ] **步骤 2：启动部署**

运行 `docker compose -f deploy/compose/docker-compose.yml build; docker compose -f deploy/compose/docker-compose.yml up -d; curl.exe -fsS http://localhost:8001/healthz`。预期健康；真实目录未达门槛时 API 健康但商城返回明确 503。

- [ ] **步骤 3：HTTP 验收与交接**

运行 `.venv\\Scripts\\python.exe scripts/commerce_e2e.py http://localhost:8001`。目录就绪时输出浏览数量；未就绪时非零退出并说明门禁原因。交接中列出每个命令的实际结果、跳过项和官网是否通过门槛。
