# 角色隔离电商平台与退赔联动实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法跟踪进度。

**目标：** 将当前项目改造成 CUSTOMER 商城、CS 客服退款审核、SV 主管审批三角色隔离的平台，并以真实抓取的品牌目录作为商城唯一商品来源。

**架构：** FastAPI 以 JWT/RBAC 拦截角色越权；目录初始化 Worker 在 PostgreSQL 保存最近一次通过门槛的抓取快照；React 按角色渲染 CustomerShell 或 BackofficeShell。退款继续复用 Ticket、Redis 审批锁和数据库条件更新。

**技术栈：** Python 3.11、FastAPI、SQLAlchemy、PostgreSQL、Redis Streams、React 18、TypeScript、Ant Design、Docker Compose、pytest。

---

## 文件清单与职责

**创建：**

- `backend/app/catalog_initialization.py`：目录门槛校验、初始化状态读写和缓存发布。
- `backend/app/worker/catalog_consumer.py`：启动初始化与每日抓取循环。
- `backend/tests/test_catalog_initialization.py`：数量、价格分区和缓存回退测试。
- `backend/tests/test_role_isolation.py`：三角色 API 隔离与退款队列测试。
- `frontend/src/components/CustomerShell.tsx`：消费者商城导航壳层。
- `frontend/src/components/BackofficeShell.tsx`：客服/主管后台壳层。
- `frontend/src/pages/ServiceRefunds.tsx`：客服人工退款队列。
- `frontend/tests/role-routing.test.mjs`：角色路由与导航静态验证。

**修改：**

- `backend/app/models.py`、`backend/migrations/20260904_add_catalog_initialization.sql`：角色与目录运行状态的显式迁移。
- `backend/app/deps.py`、`backend/app/routers/shop.py`、`backend/app/routers/tickets.py`：角色依赖、商城交易隔离和人工退款接口。
- `backend/app/commerce_service.py`：无凭证必转人工与用户退款文件关联。
- `backend/app/main.py`、`backend/app/config.py`、`deploy/compose/docker-compose.yml`：目录 Worker 和启动依赖。
- `frontend/src/App.tsx`、`frontend/src/pages/Login.tsx`、`frontend/src/styles.css`：角色首页、快捷填充和商城视觉布局。

### 任务 1：新增 CUSTOMER 角色、预置账号与交易 API 隔离

**文件：**
- 修改：`backend/app/models.py`、`backend/app/main.py`、`backend/app/deps.py`、`backend/app/routers/shop.py`
- 测试：`backend/tests/test_role_isolation.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_only_customer_can_write_cart_and_order(client, customer_headers, cs_headers):
    assert client.put('/api/shop/cart/items/1', json={'quantity': 1}, headers=cs_headers).status_code == 403
    assert client.put('/api/shop/cart/items/1', json={'quantity': 1}, headers=customer_headers).status_code != 403
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_role_isolation.py -q`

预期：失败，因为 `CUSTOMER` 枚举和角色依赖不存在。

- [ ] **步骤 3：实现最少代码**

```python
class Role(str, enum.Enum):
    CUSTOMER = 'customer'
    CS = 'cs'
    SV = 'sv'

def require_roles(*roles: Role):
    def dependency(user=Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(403, '无权访问该资源')
        return user
    return dependency
```

为 `customer_01` 添加幂等种子；商城写接口使用 `require_roles(Role.CUSTOMER)`，客服/主管接口保持既有权限。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_role_isolation.py -q`

预期：PASS，CS/SV 无法写购物车、下单或申请退款。

- [ ] **步骤 5：提交**

```bash
git add backend/app/models.py backend/app/main.py backend/app/deps.py backend/app/routers/shop.py backend/tests/test_role_isolation.py
git commit -m "feat: 增加客户角色和商城访问隔离"
```

### 任务 2：目录初始化门槛、真实缓存与失败回退

**文件：**
- 创建：`backend/app/catalog_initialization.py`、`backend/migrations/20260904_add_catalog_initialization.sql`
- 修改：`backend/app/commerce_models.py`、`backend/app/scraping/service.py`、`backend/app/routers/shop.py`
- 测试：`backend/tests/test_catalog_initialization.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_publish_requires_each_brand_twenty_skus_and_low_price(db_session):
    result = validate_catalog_snapshot({'vivo': make_skus(20, [299]), 'oppo': make_skus(19, [199])})
    assert result.status == 'INITIALIZATION_FAILED'

def test_failed_refresh_keeps_last_successful_catalog(db_session):
    publish_successful_catalog(db_session, valid_snapshot())
    assert refresh_catalog(db_session, invalid_snapshot()).used_cached_catalog is True
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_catalog_initialization.py -q`

预期：失败，因为校验器与目录状态表不存在。

- [ ] **步骤 3：实现最少代码**

```python
PRICE_BANDS = ((0, 300), (301, 3000), (3001, None))

def validate_catalog_snapshot(by_brand: dict[str, list[ProductDTO]]) -> CatalogValidation:
    required = ('vivo', 'oppo')
    if any(len(by_brand.get(brand, [])) < 20 for brand in required):
        return CatalogValidation.failed('MINIMUM_SKU_NOT_MET')
    if any(not any(item.price <= 300 for item in by_brand[brand]) for brand in required):
        return CatalogValidation.failed('LOW_PRICE_SKU_NOT_MET')
    if not all(any(in_band(item.price, low, high) for items in by_brand.values() for item in items) for low, high in PRICE_BANDS):
        return CatalogValidation.failed('PRICE_BAND_NOT_MET')
    return CatalogValidation.ready()
```

增加 `catalog_runs` 与单例可用状态，只有同次完整成功快照才能发布；没有成功缓存时产品 API 返回 `503 CATALOG_NOT_READY`。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_catalog_initialization.py backend/tests/test_scraping.py -q`

预期：PASS，失败刷新保留最近成功缓存。

- [ ] **步骤 5：提交**

```bash
git add backend/app/catalog_initialization.py backend/app/commerce_models.py backend/app/scraping/service.py backend/app/routers/shop.py backend/migrations/20260904_add_catalog_initialization.sql backend/tests/test_catalog_initialization.py
git commit -m "feat: 增加商品目录初始化门槛和缓存回退"
```

### 任务 3：消费者商城壳层、登录快捷入口与完整 UI

**文件：**
- 创建：`frontend/src/components/CustomerShell.tsx`
- 修改：`frontend/src/App.tsx`、`frontend/src/pages/Login.tsx`、`frontend/src/pages/ShopHome.tsx`、`frontend/src/pages/Cart.tsx`、`frontend/src/pages/Checkout.tsx`、`frontend/src/pages/OrderDetail.tsx`、`frontend/src/styles.css`
- 测试：`frontend/tests/role-routing.test.mjs`

- [ ] **步骤 1：编写失败测试**

```js
assert.match(source, /customer_01/)
assert.match(source, /\/shop/)
assert.doesNotMatch(customerShell, /退款工作台/)
```

- [ ] **步骤 2：运行测试验证失败**

运行：`node frontend/tests/role-routing.test.mjs`

预期：失败，因为不存在客户快捷登录与独立商城壳层。

- [ ] **步骤 3：实现最少代码**

```tsx
const homeByRole = { customer: '/shop', cs: '/service/refunds', sv: '/monitor' }
<Button onClick={() => fill('customer_01', 'secret123')}>普通用户演示账号</Button>
```

实现浅色消费者商城：品牌筛选、三价格专区、图片固定比例、加载/空/目录未初始化状态、购物车和订单页面；所有下单金额只显示后端返回值。用 `CustomerShell` 替代现有共享侧栏，客户路由不得渲染后台菜单。

- [ ] **步骤 4：运行 UI 验证**

运行：`node frontend/tests/role-routing.test.mjs; npm --prefix frontend run build`

预期：角色路由测试与 TypeScript/Vite 构建均通过。

- [ ] **步骤 5：提交**

```bash
git add frontend/src frontend/tests/role-routing.test.mjs
git commit -m "feat: 重构客户商城界面和角色登录入口"
```

### 任务 4：客服退款队列、凭证策略与并发人工审核

**文件：**
- 创建：`frontend/src/components/BackofficeShell.tsx`、`frontend/src/pages/ServiceRefunds.tsx`
- 修改：`backend/app/commerce_service.py`、`backend/app/routers/shop.py`、`backend/app/routers/tickets.py`、`frontend/src/App.tsx`
- 测试：`backend/tests/test_role_isolation.py`、`backend/tests/test_returns_api.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_return_without_evidence_is_forced_to_manual_review(client, customer_headers):
    response = create_paid_return(client, customer_headers, evidence_paths=[])
    assert response.status_code == 201
    assert ticket_for(response).status == TicketStatus.SUSPENDED

def test_cs_and_sv_cannot_both_approve_same_return(client, cs_headers, sv_headers):
    assert approve(client, cs_headers).status_code == 200
    assert approve(client, sv_headers).status_code == 409
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_role_isolation.py backend/tests/test_returns_api.py -q`

预期：失败，因为无凭证路径和客服队列尚未实现。

- [ ] **步骤 3：实现最少代码**

```python
if not evidence_paths:
    ticket.status = TicketStatus.SUSPENDED
    ticket.decision = Decision.PENDING
    ticket.decision_reasons = ['MISSING_RETURN_EVIDENCE']

@router.get('/service/returns')
def list_manual_returns(_user=Depends(require_roles(Role.CS, Role.SV)), db=Depends(get_db)):
    return db.query(ReturnRequest).join(Ticket).filter(Ticket.status == TicketStatus.SUSPENDED).all()
```

商城表单 `evidence_paths` 最少一项；后端兼容无凭证申请但强制挂起。客服页面显示待人工退款，复用既有 `approve_ticket` 锁与条件更新，不新增绕过锁的审批接口。

- [ ] **步骤 4：运行测试验证通过**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_role_isolation.py backend/tests/test_returns_api.py backend/tests/test_locks.py -q`

预期：PASS，退款人工互斥且无凭证不自动退赔。

- [ ] **步骤 5：提交**

```bash
git add backend/app/commerce_service.py backend/app/routers/shop.py backend/app/routers/tickets.py backend/tests/test_role_isolation.py backend/tests/test_returns_api.py frontend/src/components/BackofficeShell.tsx frontend/src/pages/ServiceRefunds.tsx frontend/src/App.tsx
git commit -m "feat: 增加客服退款审核队列和凭证门禁"
```

### 任务 5：Docker 目录 Worker、真实抓取验收与端到端验证

**文件：**
- 创建：`backend/app/worker/catalog_consumer.py`、`backend/tests/test_role_isolated_e2e.py`
- 修改：`backend/app/config.py`、`deploy/compose/docker-compose.yml`、`scripts/commerce_e2e.py`

- [ ] **步骤 1：编写失败测试**

```python
def test_catalog_worker_does_not_publish_invalid_first_run(monkeypatch, db_session):
    run_catalog_initialization(db_session, source_sites=['vivo', 'oppo'])
    assert get_catalog_status(db_session).status == 'INITIALIZATION_FAILED'
```

- [ ] **步骤 2：运行测试验证失败**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_role_isolated_e2e.py -q`

预期：失败，因为目录 Worker 未定义。

- [ ] **步骤 3：实现最少代码**

```python
def run_forever():
    run_catalog_initialization(SessionLocal())
    while True:
        time.sleep(settings.CATALOG_REFRESH_SECONDS)
        run_catalog_initialization(SessionLocal())
```

Compose 增加 `catalog-worker`，只挂载应用代码与数据库/Redis 连接，不挂载 Docker socket、主机目录或凭据。端到端测试覆盖三类登录定向、目录就绪门禁、客户购买/退款、客服队列和主管并发锁。

- [ ] **步骤 4：运行完整验证**

运行：`.venv\\Scripts\\python.exe -m pytest backend/tests -q; npm --prefix frontend run build; docker compose -f deploy/compose/docker-compose.yml build; docker compose -f deploy/compose/docker-compose.yml up -d; curl.exe -fsS http://localhost:8001/healthz`

预期：后端测试、前端构建、镜像构建和健康检查全部成功；首次真实目录抓取不达门槛时商城显示初始化失败而非空白或伪造商品。

- [ ] **步骤 5：提交**

```bash
git add backend/app/worker/catalog_consumer.py backend/app/config.py backend/tests/test_role_isolated_e2e.py deploy/compose/docker-compose.yml scripts/commerce_e2e.py
git commit -m "feat: 增加目录初始化 Worker 和角色电商验收"
```

## 计划自检

- 角色隔离：任务 1、3、4、5。
- 真实抓取门槛、缓存与回退：任务 2、5。
- 现代商城 UI：任务 3。
- 订单立即模拟支付、退款决策与锁：任务 4、5。
- Docker 与完整验证：任务 5。
