# 电商平台与退赔决策系统实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在现有退赔决策系统中增加可运行的模拟电商平台，完成商品浏览、购物车、地址、模拟下单、退单请求，并将退单自动接入现有决策链路。

**架构：** 采用同仓库扩展方案，在现有 FastAPI 中增加 Commerce 路由、领域服务和显式数据库迁移，在现有 React 应用中增加 `/shop` 页面。商品由固定品牌适配器每日抓取并缓存；退单通过事务和队列接口创建现有 `Ticket`，决策状态由确定性映射同步回电商域。

**技术栈：** Python 3.11、FastAPI、SQLAlchemy 2、PostgreSQL、Redis Streams、React 18、TypeScript、Ant Design、Vite、pytest。

---

## 文件清单与职责

**创建：**

- `backend/migrations/20260903_add_commerce.sql`：电商表、索引、唯一约束和外键。
- `backend/app/commerce_models.py`：商品、规格、地址、购物车、订单、退单、抓取运行模型。
- `backend/app/commerce_schemas.py`：商品、订单、退单请求/响应 DTO 和枚举。
- `backend/app/commerce_service.py`：服务端金额计算、幂等下单、模拟支付、退单建单和状态映射。
- `backend/app/scraping/base.py`：固定品牌适配器协议和标准商品 DTO。
- `backend/app/scraping/adapters.py`：vivo、OPPO 和 generic 公开页面适配器。
- `backend/app/scraping/service.py`：超时、限速、清洗、缓存 upsert 和抓取运行记录。
- `backend/app/routers/shop.py`：商品、地址、购物车、订单和退单 API。
- `backend/tests/test_commerce_service.py`：服务层金额、状态和幂等测试。
- `backend/tests/test_shop_api.py`：认证、权限、订单和退单 API 测试。
- `backend/tests/test_scraping.py`：解析成功、字段拒绝和失败保留缓存测试。
- `frontend/src/types/shop.ts`：商品、订单、退单类型。
- `frontend/src/pages/ShopHome.tsx`：商品列表、搜索和品牌筛选。
- `frontend/src/pages/ProductDetail.tsx`：商品详情、规格和加购。
- `frontend/src/pages/Cart.tsx`：购物车编辑和结算入口。
- `frontend/src/pages/Checkout.tsx`：地址选择、订单确认和模拟支付。
- `frontend/src/pages/Orders.tsx`：我的订单列表。
- `frontend/src/pages/OrderDetail.tsx`：订单详情和退单入口。
- `frontend/src/pages/Returns.tsx`：退单列表和决策状态。

**修改：**

- `backend/app/models.py`：导入电商模型，确保 metadata 注册。
- `backend/app/main.py`：注册 `shop` 路由。
- `backend/app/routers/tickets.py`：在详情响应中加入可选订单关联摘要。
- `backend/app/worker/consumer.py`：复用并明确退单工单的上下文/状态更新钩子。
- `frontend/src/App.tsx`：增加电商路由和登录后跳转规则。
- `frontend/src/components/AppShell.tsx`：增加用户端导航入口，保留主管后台导航。
- `frontend/src/api/client.ts`：保留 `/api` 基址，补充幂等键请求辅助函数。
- `frontend/src/styles.css`：增加商品网格、订单状态和移动端布局样式。
- `deploy/compose/docker-compose.yml`：增加 `SCRAPE_SCHEDULE`、允许来源配置和 worker 抓取环境变量。

---

### 任务 1：领域枚举、迁移和模型

**文件：**
- 创建：`backend/migrations/20260903_add_commerce.sql`
- 创建：`backend/app/commerce_models.py`
- 修改：`backend/app/models.py`
- 测试：`backend/tests/test_commerce_service.py`

- [ ] **步骤 1：编写失败测试**

为 `test_commerce_service.py` 添加模型枚举和唯一约束测试：订单明细必须保存商品快照，`orders.idempotency_key` 和 `return_requests.ticket_id` 不得重复。

- [ ] **步骤 2：运行测试确认失败**

运行：`python -m pytest backend/tests/test_commerce_service.py -q`

预期：因 `commerce_models` 和表结构不存在而失败。

- [ ] **步骤 3：实现最少模型和 SQL**

定义文档中的 8 个实体、状态枚举、外键、时间字段及 `source_site + external_id`、订单幂等键、退单 ticket 关联唯一约束。迁移使用 `CREATE TABLE IF NOT EXISTS` 和显式索引，不修改既有表结构。

- [ ] **步骤 4：运行测试确认通过**

运行：`python -m pytest backend/tests/test_commerce_service.py -q`

预期：模型导入、枚举和约束测试通过。

- [ ] **步骤 5：Commit**

```bash
git add backend/migrations/20260903_add_commerce.sql backend/app/commerce_models.py backend/app/models.py backend/tests/test_commerce_service.py
git commit -m "feat: 增加电商领域模型和迁移"
```

### 任务 2：商品查询和爬取缓存

**文件：**
- 创建：`backend/app/commerce_schemas.py`
- 创建：`backend/app/scraping/base.py`
- 创建：`backend/app/scraping/adapters.py`
- 创建：`backend/app/scraping/service.py`
- 创建：`backend/tests/test_scraping.py`
- 创建：`backend/app/routers/shop.py`
- 修改：`backend/app/main.py`

- [ ] **步骤 1：编写失败测试**

测试标准 DTO 能接受品牌、SKU、名称、价格、图片和来源 URL；测试无 HTTPS、无名称、非正价格会被拒绝；测试适配器失败后旧商品仍为 `ACTIVE`，`scrape_runs` 为 `FAILED`。

- [ ] **步骤 2：运行测试确认失败**

运行：`python -m pytest backend/tests/test_scraping.py -q`

预期：适配器和抓取服务尚未定义而失败。

- [ ] **步骤 3：实现固定来源适配器**

实现 `BrandAdapter.parse(response_text, source_url) -> list[ProductDTO]`。来源 URL 只能来自代码配置；使用 `httpx.AsyncClient` 的固定超时、每来源并发 1 和间隔 1 秒。解析错误写入 `scrape_runs`，禁止清空缓存。

- [ ] **步骤 4：实现商品只读 API**

在 `shop.py` 实现 `GET /api/shop/products`、`GET /api/shop/products/{id}`、`GET /api/shop/brands`，支持分页、关键词、品牌和价格过滤。商品列表不触发网络抓取。

- [ ] **步骤 5：运行测试确认通过**

运行：`python -m pytest backend/tests/test_scraping.py -q backend/tests/test_shop_api.py -q`

预期：解析、缓存保留和商品查询测试通过。

- [ ] **步骤 6：Commit**

```bash
git add backend/app/commerce_schemas.py backend/app/scraping backend/app/routers/shop.py backend/app/main.py backend/tests/test_scraping.py
git commit -m "feat: 增加商品目录和缓存抓取"
```

### 任务 3：地址、购物车和订单服务

**文件：**
- 修改：`backend/app/commerce_schemas.py`
- 创建：`backend/app/commerce_service.py`
- 修改：`backend/app/routers/shop.py`
- 创建：`backend/tests/test_commerce_service.py`
- 创建：`backend/tests/test_shop_api.py`

- [ ] **步骤 1：编写失败测试**

覆盖：游客访问地址/购物车/订单返回 401；服务端按商品快照计算总额；重复 `X-Idempotency-Key` 返回同一订单；地址只能由所属用户读取或修改。

- [ ] **步骤 2：运行测试确认失败**

运行：`python -m pytest backend/tests/test_shop_api.py -q`

预期：路由和服务不存在或返回 404。

- [ ] **步骤 3：实现地址和购物车接口**

实现地址 CRUD、默认地址唯一逻辑和用户隔离；购物车使用用户维度记录，数量限制为正整数，商品规格不存在或不可售时返回 409。

- [ ] **步骤 4：实现幂等订单创建**

在事务中锁定可售规格，重新读取价格，写入 `address_snapshot_json` 与 `product_snapshot_json`，计算 `total_amount`，并用数据库唯一约束处理并发重复键。

- [ ] **步骤 5：运行测试确认通过**

运行：`python -m pytest backend/tests/test_commerce_service.py backend/tests/test_shop_api.py -q`

预期：权限、金额快照和订单幂等测试通过。

- [ ] **步骤 6：Commit**

```bash
git add backend/app/commerce_schemas.py backend/app/commerce_service.py backend/app/routers/shop.py backend/tests/test_commerce_service.py backend/tests/test_shop_api.py
git commit -m "feat: 增加地址购物车和订单接口"
```

### 任务 4：模拟支付与用户订单查询

**文件：**
- 修改：`backend/app/commerce_service.py`
- 修改：`backend/app/routers/shop.py`
- 修改：`backend/tests/test_shop_api.py`

- [ ] **步骤 1：编写失败测试**

测试只有 `CREATED` 订单可模拟支付；重复支付保持幂等；支付接口不接受银行卡字段且不会调用外部支付客户端。

- [ ] **步骤 2：运行测试确认失败**

运行：`python -m pytest backend/tests/test_shop_api.py -k payment -q`

预期：支付接口尚未存在而失败。

- [ ] **步骤 3：实现模拟支付**

实现 `POST /api/shop/orders/{order_id}/simulate-pay`，使用条件更新 `status = CREATED`，成功后改为 `PAID_SIMULATED`；已支付订单直接返回当前状态，其他终态返回 409。

- [ ] **步骤 4：验证订单查询隔离**

实现用户分页订单列表和详情接口；主管只能通过现有 RBAC 访问后台关联上下文，不改变普通用户的数据范围。

- [ ] **步骤 5：运行测试并提交**

运行：`python -m pytest backend/tests/test_shop_api.py -k "payment or order" -q`

预期：全部通过。

```bash
git add backend/app/commerce_service.py backend/app/routers/shop.py backend/tests/test_shop_api.py
git commit -m "feat: 增加模拟支付和订单查询"
```

### 任务 5：退单建单和状态同步

**文件：**
- 修改：`backend/app/commerce_service.py`
- 修改：`backend/app/routers/shop.py`
- 修改：`backend/app/routers/tickets.py`
- 修改：`backend/app/worker/consumer.py`
- 修改：`backend/tests/test_shop_api.py`

- [x] **步骤 1：编写失败测试**

覆盖：仅 `PAID_SIMULATED` 订单可退单；重复幂等键只创建一个 `return_request` 和一个 `ticket`；退单描述和凭证路径传入工单；决策枚举按固定映射更新退单状态。

- [x] **步骤 2：运行测试确认失败**

运行：`python -m pytest backend/tests/test_shop_api.py -k return -q`

预期：退单接口和状态映射尚未实现而失败。

- [x] **步骤 3：实现事务性退单创建**

在单事务中校验订单归属和订单状态，写入退单及明细状态，创建现有 Ticket 并投递 Redis Streams；队列失败时写入 `FAILED` 和错误码后回滚或显式落库，禁止返回虚假的 `PROCESSING`。

- [x] **步骤 4：实现确定性状态映射**

增加 `map_ticket_to_return_status(ticket_status, decision)` 函数，严格使用设计文档中的五条映射；不调用 LLM，不改变现有审批锁和条件更新。

- [x] **步骤 5：运行测试确认通过**

运行：`python -m pytest backend/tests/test_shop_api.py -k return -q backend/tests/test_idempotency.py backend/tests/test_locks.py -q`

预期：退单、既有幂等和审批锁测试全部通过。

- [ ] **步骤 6：Commit**

```bash
git add backend/app/commerce_service.py backend/app/routers/shop.py backend/app/routers/tickets.py backend/app/worker/consumer.py backend/tests/test_shop_api.py
git commit -m "feat: 将退单接入退赔决策链路"
```

### 任务 6：电商前端页面与导航

**文件：**
- 创建：`frontend/src/types/shop.ts`
- 创建：`frontend/src/pages/ShopHome.tsx`
- 创建：`frontend/src/pages/ProductDetail.tsx`
- 创建：`frontend/src/pages/Cart.tsx`
- 创建：`frontend/src/pages/Checkout.tsx`
- 创建：`frontend/src/pages/Orders.tsx`
- 创建：`frontend/src/pages/OrderDetail.tsx`
- 创建：`frontend/src/pages/Returns.tsx`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/components/AppShell.tsx`
- 修改：`frontend/src/styles.css`

- [ ] **步骤 1：先运行前端构建确认基线**

运行：`npm --prefix frontend run build`

预期：基线构建通过。

- [ ] **步骤 2：实现商品和购物车页面**

使用现有 Ant Design 和 axios 封装，商品页支持加载、空态、错误重试、品牌筛选、分页；详情页选择规格和数量；购物车支持修改数量、删除和未登录跳转登录。

- [ ] **步骤 3：实现结算、订单和退单页面**

结算页展示服务端返回金额和地址；模拟支付按钮只调用 simulate-pay；订单详情显示商品快照；退单表单提交原因、说明和凭证，并显示五类状态文案。

- [ ] **步骤 4：接入路由和导航**

游客默认进入 `/shop`；登录用户保留现有客服/主管跳转规则；用户端导航增加商品、购物车、订单、退单，主管后台菜单不被覆盖。

- [ ] **步骤 5：运行构建确认通过**

运行：`npm --prefix frontend run build`

预期：TypeScript 和 Vite 构建通过，无未使用导入错误。

- [ ] **步骤 6：Commit**

```bash
git add frontend/src
git commit -m "feat: 增加电商用户端页面"
```

### 任务 7：调度配置、后台上下文和可观测性

**文件：**
- 修改：`deploy/compose/docker-compose.yml`
- 修改：`backend/app/worker/consumer.py`
- 修改：`backend/app/routers/tickets.py`
- 修改：`backend/app/config.py`
- 创建：`backend/tests/test_commerce_observability.py`

- [ ] **步骤 1：编写失败测试**

测试订单号、退单号和 ticket_id 出现在结构化事件字段中；敏感字段不出现在日志；未配置 CubeSandbox 时相关沙箱路径仍显式失败。

- [ ] **步骤 2：实现配置和日志字段**

增加固定来源配置、抓取每日调度配置和请求关联字段；复用现有 telemetry 异步上报，不阻塞 API 主循环，不记录 Token、密码、API Key、图片原文。

- [ ] **步骤 3：增加后台订单摘要**

Ticket 详情响应只加入关联订单号、商品名称、退单原因等最小摘要；客服仍只能查看自己创建的工单，主管沿用现有 RBAC。

- [ ] **步骤 4：运行测试确认通过**

运行：`python -m pytest backend/tests/test_commerce_observability.py backend/tests/test_security.py backend/tests/test_sandbox.py -q`

预期：新增和既有安全测试通过。

- [ ] **步骤 5：Commit**

```bash
git add deploy/compose/docker-compose.yml backend/app/worker/consumer.py backend/app/routers/tickets.py backend/app/config.py backend/tests/test_commerce_observability.py
git commit -m "feat: 增加电商调度配置和审计上下文"
```

### 任务 8：端到端验收与稳定性

**文件：**
- 创建：`backend/tests/test_commerce_e2e.py`
- 创建：`scripts/commerce_e2e.py`
- 修改：`specs/001-refund-decision-mvp/quickstart.md`

- [ ] **步骤 1：编写端到端失败场景**

覆盖游客浏览、登录、地址、加购、幂等下单、模拟支付、退单建 ticket、自动退款和人工审批两条路径；加入并发重复下单/退单场景。

- [ ] **步骤 2：运行端到端测试确认失败原因**

运行：`python -m pytest backend/tests/test_commerce_e2e.py -q`

预期：新增电商接口或联调步骤缺失时明确失败。

- [ ] **步骤 3：实现独立验收脚本**

脚本使用固定演示账号和随机幂等键，只调用 HTTP 接口，不执行 shell 命令；输出每个阶段的订单号、退单号和决策状态，失败时返回非零退出码。

- [ ] **步骤 4：运行完整检查**

运行：`make check`、`npm --prefix frontend run build`、`python scripts/commerce_e2e.py http://localhost:8001`。

预期：后端现有测试、前端构建、电商测试和核心两条退单路径全部通过；外部品牌站点不可用时目录仍可读。

- [ ] **步骤 5：更新快速开始并提交**

在 `quickstart.md` 增加电商入口、演示账号、模拟支付说明和验收脚本命令。

```bash
git add backend/tests/test_commerce_e2e.py scripts/commerce_e2e.py specs/001-refund-decision-mvp/quickstart.md
git commit -m "test: 增加电商端到端验收"
```

## 计划自检

- 规格覆盖：商品目录/爬取（任务 1-2）、地址/购物车/订单/模拟支付（任务 3-4）、退单接入和状态同步（任务 5）、用户页面（任务 6）、安全/观测/配置（任务 7）、验收与文档（任务 8）。
- 数据一致性：`order_id`、`order_item_id`、`return_request.ticket_id` 在任务 1 定义，在任务 5 创建并在任务 8 验证。
- 幂等一致性：订单和退单均使用 `X-Idempotency-Key`，任务 3、5 分别覆盖并发和重放。
- 外部依赖边界：爬虫只在任务 2/7 的固定配置中访问公开 URL，用户请求链路不调用爬虫。
- 无占位步骤：每个任务均包含具体文件、失败测试、命令、实现边界和提交点。
