# 商品目录覆盖与品牌标识接入实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为商城提供稳定的手机和外设专区，并在顾客与运营端显示已交付的「确认路径」Logo。

**架构：** 在 `products.category` 持久化确定性分类。目录抓取将官方分类和名称映射为 `PHONE`、`PERIPHERAL`、`OTHER`，只有品牌、价格和品类覆盖同时达标时才原子发布。API 使用分类查询，前端不再以名称关键词定义专区；两个壳组件只引用本地 SVG 资产。

**技术栈：** FastAPI、SQLAlchemy、PostgreSQL/SQLite 显式迁移、React、TypeScript、Vitest、pytest。

---

## 文件结构

- 创建：`backend/migrations/20260909_add_product_category.sql`：回填并索引 `products.category`。
- 修改：`backend/app/commerce_models.py`、`backend/app/commerce_schemas.py`：领域字段与 API 模型。
- 修改：`backend/app/scraping/adapters.py`、`backend/app/scraping/service.py`：确定性分类和官方多入口快照。
- 修改：`backend/app/catalog_initialization.py`、`backend/app/worker/catalog_consumer.py`：品类发布门槛及索引失败隔离。
- 修改：`backend/app/routers/shop.py`：分类查询与响应字段。
- 修改：`frontend/src/types/shop.ts`、`frontend/src/pages/ShopHome.tsx`、`frontend/src/components/CustomerShell.tsx`、`frontend/src/components/AppShell.tsx`、`frontend/src/styles.css`：专区筛选和 SVG 品牌标识。
- 修改：`backend/tests/test_scraping.py`、`backend/tests/test_catalog_initialization.py`、`backend/tests/test_shop_api.py`、`frontend/src/pages/ShopHome.test.tsx`、`frontend/src/components/CustomerShell.test.tsx`；创建 `frontend/src/components/AppShell.test.tsx`：行为回归测试。

### 任务 1：锁定失败测试与数据库迁移

- [ ] **步骤 1：添加失败测试**

在后端测试中断言：`classify_category("手机", "REDMI K100 Pro") == "PHONE"`、`classify_category("耳机", "vivo TWS 5") == "PERIPHERAL"`、未知商品为 `OTHER`；候选快照少于 12 台手机或少于 20 个外设时返回对应失败码。

- [ ] **步骤 2：运行失败测试**

运行：`& .venv\Scripts\python.exe -m pytest backend/tests/test_scraping.py backend/tests/test_catalog_initialization.py -q`

预期：FAIL，缺少 `classify_category` 或缺少新发布门槛。

- [ ] **步骤 3：新增显式迁移**

创建 SQL：

```sql
ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(16) NOT NULL DEFAULT 'OTHER';
CREATE INDEX IF NOT EXISTS ix_products_category ON products (category);
```

同时把 `Product.category` 默认值设为 `OTHER`，不改动订单快照、购物车或退款表。

- [ ] **步骤 4：运行迁移与模型测试**

运行：`& .venv\Scripts\python.exe -m pytest backend/tests/test_scraping.py backend/tests/test_catalog_initialization.py -q`

预期：仍仅因分类实现缺失失败。

### 任务 2：实现确定性分类与原子目录发布

- [ ] **步骤 1：实现分类和 DTO 透传**

为 DTO、模型与产品响应添加 `category`；适配器以官方分类优先、商品名称回退的固定关键字表进行分类，禁止模型调用或响应内容定义规则。

- [ ] **步骤 2：实施目录发布门槛**

在 `validate_catalog_snapshot` 中保持双品牌每个至少 20 条和三档价格验证，并增加 `PHONE >= 12`、`PERIPHERAL >= 20`。失败使用 `PHONE_COVERAGE_NOT_MET` 或 `PERIPHERAL_COVERAGE_NOT_MET`。

- [ ] **步骤 3：隔离索引失败**

在目录 Worker 中，目录发布成功后即提交；消费者知识库索引失败只记录异常，不回滚目录发布。

- [ ] **步骤 4：运行后端分类与目录测试**

运行：`& .venv\Scripts\python.exe -m pytest backend/tests/test_scraping.py backend/tests/test_catalog_initialization.py -q`

预期：PASS。

### 任务 3：提供按分类筛选的商品 API

- [ ] **步骤 1：添加 API 失败测试**

在 `test_shop_api.py` 创建一个 `PHONE` 和一个 `PERIPHERAL` 商品，断言 `GET /api/shop/products?category=PHONE` 只返回手机，`category=INVALID` 返回 422，响应包含 `category`。

- [ ] **步骤 2：运行 API 失败测试**

运行：`& .venv\Scripts\python.exe -m pytest backend/tests/test_shop_api.py -q`

预期：FAIL，因为 API 尚未接收 `category` 或响应尚未提供该字段。

- [ ] **步骤 3：实现白名单分类查询**

在路由使用 `Literal["PHONE", "PERIPHERAL", "OTHER"] | None` 查询参数并过滤 `Product.category`；保留现有品牌、价格、分页、目录状态和权限行为。

- [ ] **步骤 4：运行 API 测试**

运行：`& .venv\Scripts\python.exe -m pytest backend/tests/test_shop_api.py -q`

预期：PASS。

### 任务 4：以分类定义商城专区并接入 Logo

- [ ] **步骤 1：添加前端失败测试**

在 `ShopHome.test.tsx` 断言点击“手机”后请求参数为 `category: "PHONE"`，并补充 `CustomerShell`、`AppShell` 测试断言本地 SVG 的 `img` 存在且品牌文字可访问。

- [ ] **步骤 2：运行前端失败测试**

运行：`npm --prefix frontend test -- ShopHome.test.tsx CustomerShell.test.tsx AppShell.test.tsx --run`

预期：FAIL，因为专区仍使用 `keyword` 且壳组件未引用 SVG。

- [ ] **步骤 3：实现筛选与 Logo 引用**

扩展前端商品类型，使用 URL 参数 `category` 组合搜索、品牌和价格筛选；顾客页头引用横向与图标 SVG，主管/客服侧栏引用反白 SVG，CSS 在窄屏/折叠时隐藏文字但保留图标。

- [ ] **步骤 4：运行前端相关测试**

运行：`npm --prefix frontend test -- ShopHome.test.tsx CustomerShell.test.tsx AppShell.test.tsx --run`

预期：PASS。

### 任务 5：回归验证与提交

- [ ] **步骤 1：运行完整后端测试**

运行：`& .venv\Scripts\python.exe -m compileall -q backend scripts; & .venv\Scripts\python.exe -m pytest backend/tests -q`

预期：退出码 0。

- [ ] **步骤 2：运行前端生产构建**

运行：`npm --prefix frontend run build`

预期：退出码 0；允许既有 bundle 大小提示。

- [ ] **步骤 3：检查变更范围**

运行：`git diff --check; git status --short`

预期：无空白错误；不暂存 `docs/evidence/periodic-eval-report.md` 或 `tmp/`。

- [ ] **步骤 4：提交实现**

```powershell
git add backend frontend docs/superpowers/plans/2026-09-09-catalog-coverage-and-logo-adoption.md
git commit -m "feat: 扩充商城专区并接入品牌标识"
```

预期：提交仅包含本计划的分类、目录、Logo、测试、迁移与计划文件。

## 自检结果

- 规格覆盖：任务 1-2 覆盖兼容迁移、分类、门槛、缓存发布和 Worker 隔离；任务 3 覆盖 API；任务 4 覆盖前端专区和 Logo；任务 5 覆盖全量验证。
- 一致性：分类值在迁移、模型、API、测试和前端中统一为 `PHONE`、`PERIPHERAL`、`OTHER`。
- 范围：不增加第三方来源，不变更认证、订单、退款或真实支付语义。
