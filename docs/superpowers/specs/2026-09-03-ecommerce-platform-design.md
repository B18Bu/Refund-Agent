# 电商平台与退赔决策系统实现文档

## 1. 文档目的

为现有“客诉舆情退赔决策系统”增加一个可运行的模拟电商平台，使普通用户能够浏览商品、提交订单和发起退单，并验证退单进入现有 OCR、风控、舆情和人工审批链路的完整过程。

本阶段不接入真实支付、不产生真实资金结算。商品数据通过定时抓取公开品牌页面获得，同时保留本地缓存，避免外部网站波动影响演示。

## 2. 已确认范围

- 游客可以浏览、搜索和筛选商品。
- 登录后才能保存收货地址、加入购物车、提交订单、查看订单和发起退单。
- 支持手机号或邮箱登录/注册；第一期可沿用现有账号体系并补充用户资料字段。
- 商品来源包括 vivo、OPPO 及其他公开品牌页面。
- 爬虫每天定时运行一次，商品页读取本地缓存；本次抓取失败时保留上次成功数据并记录失败原因。
- 订单使用模拟支付，页面只显示模拟支付成功，不采集银行卡、支付密码或真实支付凭证。
- 用户从订单发起退单后，系统自动创建现有退赔决策工单。
- 电商订单、订单明细、退单请求与决策工单建立关联，并向用户同步决策状态。
- 现有 JWT/RBAC、幂等键、审批锁、确定性决策规则和沙箱约束继续有效。

## 3. 非目标

- 不接入微信、支付宝、银行卡或任何真实支付渠道。
- 不承诺从品牌网站抓取全部商品；只处理已配置、允许访问且结构稳定的公开页面。
- 不实现真实库存扣减、物流接口、发票、优惠券、营销活动和售后财务结算。
- 不允许用户提交 URL 来动态控制爬虫目标。

## 4. 推荐架构

采用“同仓库扩展”方案：在现有 FastAPI + React + PostgreSQL + Redis Compose 中增加电商模块。

```text
用户浏览器
    │
    ├── React 电商页面：商品 / 购物车 / 订单 / 退单
    │
    └── Commerce API（现有 FastAPI 内新增路由）
          ├── 商品目录与缓存
          ├── 地址、购物车、订单、模拟支付
          ├── 退单请求与订单关联
          └── 调用现有 Tickets API / 决策队列

定时爬取 Worker
    └── 固定品牌适配器 → 清洗校验 → 商品缓存 → scrape_runs

现有决策 Worker
    └── OCR → 风控 → 舆情 → 金额决策 → 人工审批
```

电商模块与退赔模块共享认证和数据库，但通过明确的订单/退单服务接口通信。退赔决策仍是唯一的审批事实来源，电商平台只保存关联关系和面向用户的状态映射。

## 5. 用户流程

### 5.1 浏览与选购

1. 游客进入首页，查看品牌、商品列表和商品详情。
2. 用户按品牌、关键词、价格区间和商品状态筛选。
3. 登录用户选择商品规格和数量，加入购物车。

### 5.2 下单

1. 用户确认购物车。
2. 选择或新增收货地址。
3. 创建订单，服务端重新读取商品快照和价格，不能信任前端金额。
4. 进入模拟支付页并确认“模拟支付成功”。
5. 订单状态变为 `PAID_SIMULATED`，用户可在订单详情查看商品快照和金额。

### 5.3 退单

1. 仅允许对符合条件的订单明细发起退单。
2. 用户填写退单原因、说明和可选凭证。
3. 服务端使用幂等键创建 `return_request`，并自动创建现有 `ticket`。
4. 决策后台处理工单；电商端显示“处理中、待人工审核、已批准、已拒绝、处理失败”。
5. 主管审批后，订单明细和退单请求获得最终状态；模拟退款只更新业务状态，不调用支付接口。

## 6. 数据模型

新增表（字段名使用英文，中文说明用于文档）：

### `products`

- `id`、`brand`、`name`、`model`、`description`
- `source_url`、`source_site`、`image_url`
- `status`（`ACTIVE` / `UNAVAILABLE`）、`last_synced_at`
- `created_at`、`updated_at`

### `product_variants`

- `id`、`product_id`
- `sku`、`variant_name`、`spec_json`
- `price`、`currency`（固定 `CNY`）、`available`

### `product_sources`

- `id`、`product_id`、`source_site`、`source_url`
- `external_id`、`raw_hash`、`last_seen_at`
- 对 `source_site + external_id` 建唯一约束，避免重复商品。

### `addresses`

- `id`、`user_id`、`recipient_name`、`phone`
- `province`、`city`、`district`、`detail`
- `is_default`、`created_at`、`updated_at`

### `orders`

- `id`、`order_no`、`user_id`、`address_snapshot_json`
- `status`（`CREATED` / `PAID_SIMULATED` / `RETURNING` / `RETURN_COMPLETED` / `CLOSED`）
- `total_amount`、`currency`、`idempotency_key`
- `created_at`、`updated_at`

### `order_items`

- `id`、`order_id`、`product_id`、`variant_id`
- `product_snapshot_json`、`quantity`、`unit_price`
- `status`（`NORMAL` / `RETURN_REQUESTED` / `RETURN_APPROVED` / `RETURN_REJECTED`）

### `return_requests`

- `id`、`return_no`、`order_id`、`order_item_id`、`user_id`
- `reason`、`description`、`evidence_paths`
- `status`（`SUBMITTED` / `PROCESSING` / `PENDING_REVIEW` / `APPROVED` / `REJECTED` / `FAILED`）
- `ticket_id`（唯一，可空但创建决策后必须存在）
- `idempotency_key`、`created_at`、`updated_at`

### `scrape_runs`

- `id`、`source_site`、`started_at`、`ended_at`
- `status`（`RUNNING` / `SUCCESS` / `PARTIAL` / `FAILED`）
- `items_seen`、`items_upserted`、`error_message`

生产环境新增字段和表必须使用显式 SQL 迁移，禁止依赖 `create_all` 修改已有数据库。

## 7. API 设计

所有接口使用现有 `/api` 前缀、JWT 认证和统一错误格式。

### 商品

- `GET /api/shop/products`：分页、关键词、品牌、价格筛选。
- `GET /api/shop/products/{id}`：商品详情和可售规格。
- `GET /api/shop/brands`：返回已同步品牌。

### 地址与购物车

- `GET/POST /api/shop/addresses`
- `PUT/DELETE /api/shop/addresses/{id}`
- `GET /api/shop/cart`
- `PUT /api/shop/cart/items/{variant_id}`
- `DELETE /api/shop/cart/items/{variant_id}`

### 订单

- `POST /api/shop/orders`：必须携带 `X-Idempotency-Key`。
- `GET /api/shop/orders`：用户只可查看自己的订单，主管可按权限查看关联退单上下文。
- `GET /api/shop/orders/{order_id}`
- `POST /api/shop/orders/{order_id}/simulate-pay`

### 退单

- `POST /api/shop/orders/{order_id}/returns`：创建退单并自动建决策工单，必须携带幂等键。
- `GET /api/shop/returns`
- `GET /api/shop/returns/{return_id}`

服务端必须在事务中创建订单/退单关联，在队列投递失败时显式记录失败状态，不得返回“处理中”而丢失工单。

## 8. 商品爬取设计

- 每个品牌实现一个固定适配器，统一输出标准商品 DTO。
- 只访问配置文件中的 HTTPS 公开页面；不接受用户提供目标 URL。
- 使用超时、并发上限、请求间隔和重试上限；遵守站点 robots、服务条款和适用法律。
- 解析失败、网络超时、限流和字段缺失都写入 `scrape_runs`，单个来源失败不得清空已有商品。
- 图片优先保存来源 URL；如需本地缓存，限制大小和 MIME，并禁止执行上传内容。
- 定时任务默认每天执行一次，也提供主管权限的手动重跑接口（后续阶段）。
- 前台只读成功同步的数据，显示“数据更新时间”，不在用户请求链路中实时抓取。

## 9. 状态映射

| 决策后台 | 电商退单 | 用户文案 |
|---|---|---|
| `PENDING` + `RUNNING` | `PROCESSING` | 处理中 |
| `PENDING` + `SUSPENDED` | `PENDING_REVIEW` | 待人工审核 |
| `AUTO_REFUNDED` / `APPROVED` | `APPROVED` | 退单已通过（模拟退款） |
| `REJECTED` | `REJECTED` | 退单未通过 |
| `FAILED` | `FAILED` | 处理失败，请联系客服 |

映射必须由确定性代码完成，不能由 LLM 决定。后台工单仍保留完整 OCR、风控、舆情、审批和错误信息。

## 10. 前端页面

- `/shop`：商品首页、品牌筛选和搜索。
- `/shop/products/:id`：商品详情、规格和加入购物车。
- `/shop/cart`：购物车确认。
- `/shop/checkout`：地址选择、订单确认和模拟支付入口。
- `/shop/orders`：我的订单列表。
- `/shop/orders/:id`：订单详情、模拟支付和退单入口。
- `/shop/returns`：我的退单及决策状态。

现有后台页面继续保留。主管查看退赔工单时增加订单号、商品快照和退单原因；客服与普通用户不能越权查看他人订单或退单。

## 11. 可靠性与安全要求

- 订单创建、模拟支付、退单创建全部支持幂等键和数据库唯一约束。
- 金额由服务端根据商品快照计算；前端金额仅用于展示。
- 退单凭证沿用现有文件校验、大小限制和隔离存储策略。
- 用户输入的商品搜索词、退单描述和 OCR 文本均是不可信数据，不能改变系统规则或工具权限。
- 爬虫和数据清洗不得使用 `shell=True`，不得执行网页中的脚本或命令。
- 外部品牌站点不可用时，商品目录仍可读；错误可在管理员诊断接口中查看。
- API、爬虫和决策队列分别记录请求 ID、订单号、退单号、ticket_id 和错误码，禁止记录密码、Token、API Key、原始图片。

## 12. 实施阶段

### Phase 1：领域模型与只读商品目录

新增迁移、模型、商品查询 API、品牌/筛选接口和前端商品列表/详情；先使用种子数据验证页面和权限。

### Phase 2：爬虫与缓存

实现品牌适配器、定时任务、清洗校验、失败保留旧数据和抓取运行记录。先接入一个品牌适配器，再扩展到 OPPO、vivo 和其他来源。

### Phase 3：购物车、地址、订单和模拟支付

实现地址簿、购物车、订单快照、幂等下单、模拟支付和用户订单页面。

### Phase 4：退单与决策系统联调

实现退单请求、凭证上传、自动创建 ticket、状态同步和用户退单页面；补充后台订单上下文。

### Phase 5：验收与稳定性

执行现有 `make check`、后端 API 测试、前端构建、爬取失败回退测试、订单/退单并发幂等测试和端到端场景验证。

## 13. 验收标准

- 游客可以稳定浏览商品；未登录访问用户订单接口返回 401。
- 登录用户可以维护多个地址、创建订单并完成模拟支付；重复幂等键不会创建重复订单。
- 订单保存商品和地址快照，后续商品价格变化不影响历史订单。
- 已支付订单可以提交退单；重复提交只产生一个退单请求和一个决策工单。
- 退单状态能从决策后台同步到用户端，审批并发仍遵守现有锁和条件更新。
- 爬虫成功时更新目录；超时、限流或解析失败时保留旧数据并产生可查询的失败记录。
- 不存在真实支付调用，不落库银行卡或支付密码。
- 现有后端测试、前端构建、Golden Dataset、沙箱拒绝测试和新增电商测试全部通过。

## 14. 待规划阶段确认的事项

以下事项不阻塞本设计，但应在实现计划中明确：品牌页面具体 URL 和字段映射、爬虫运行时刻、商品图片是否本地缓存、用户注册验证方式、订单可退时间窗口，以及是否提供管理员手动触发抓取页面。

