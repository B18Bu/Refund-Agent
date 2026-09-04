# 任务五：目录 Worker 与电商端到端验收设计

## 目标与范围

完成既定电商改造计划的任务五：以独立 Docker 目录 Worker 在启动时联网抓取固定的 vivo、OPPO 官网公开来源，并以目录门禁、端到端测试和 Compose 验收保证商城只展示通过校验的真实商品。

本任务不调整既有商城页面布局；仅验证已有的目录初始化失败、加载和可售页面状态。既有 JWT/RBAC、退款审批锁、Redis 幂等键、退款决策流和数据库迁移策略不在修改范围内。

## 成功标准

- Worker 启动后立即抓取 vivo 与 OPPO，之后每 24 小时刷新一次。
- 同一轮抓取只有两个品牌均成功、且快照满足既有 SKU 数量和价格分区门槛时，才能发布目录。
- 首次抓取失败时目录明确为 `INITIALIZATION_FAILED`，商品 API 保持 `503 CATALOG_NOT_READY`，不展示或销售伪造、部分或宿主机商品。
- 成功目录后的刷新失败保留上一次已发布目录，并记录本轮失败原因。
- Compose 中的 `catalog-worker` 无 Docker socket、宿主机目录、上传目录、凭据或 SSH 密钥挂载。
- 后端测试、前端构建、Compose 构建与健康检查提供可复现的验证证据。

## 架构与数据流

1. `catalog-worker` 创建独立数据库会话并执行单轮目录初始化。
2. 初始化逻辑仅遍历代码固定的 `vivo`、`oppo`；不接受用户 URL 或动态来源。
3. 每个来源请求使用现有 HTTPS、超时、限速和字段校验；结果先聚合为内存 `ProductDTO` 快照，不在抓取阶段写入可售商品。
4. 当两个来源均成功后，调用既有 `validate_catalog_snapshot` 校验每品牌至少 20 个 SKU、每品牌至少一个 `<=300` 商品，以及全目录三个价格区间。
5. 校验成功时，在一个事务内 upsert 产品、规格、来源和目录状态，最后设置 `READY` 与 `last_success_at`。
6. 校验或抓取失败时：若没有成功缓存，写入 `INITIALIZATION_FAILED` 和错误码；若已有 `READY` 缓存，则保留原商品和 `READY`，记录本轮失败原因。
7. Worker 通过 `try/finally` 关闭会话，异常不会传入 API 主事件循环；等待 `CATALOG_REFRESH_SECONDS` 后进行下一轮。

## 组件边界

- `backend/app/scraping/service.py`：保留现有单来源抓取和更新行为，新增只抓取并返回 DTO 快照的受控入口；不负责目录发布。
- `backend/app/catalog_initialization.py`：编排两品牌快照、门槛判断、首次失败/缓存回退语义和原子发布。
- `backend/app/worker/catalog_consumer.py`：运行一次初始化和周期循环；不处理退款 Stream。
- `backend/app/config.py`：增加 `CATALOG_REFRESH_SECONDS`，默认 86400 秒。
- `deploy/compose/docker-compose.yml`：新增最小权限的 `catalog-worker` 服务，等待 PostgreSQL 与 Redis 健康后启动。
- `backend/tests/test_role_isolated_e2e.py` 与 `scripts/commerce_e2e.py`：覆盖部署后 API 链路和失败语义。

## 错误语义与安全约束

- 单一来源失败、响应不可解析、来源不在白名单、SKU/价格门槛不足均阻止本轮首次发布。
- 抓取网页为不可信数据，仅经适配器转换为已校验 DTO；页面内容不能改变来源、权限或执行任何命令。
- API 端不触发网络抓取。目录未就绪时沿用 `503 CATALOG_NOT_READY`。
- 目录 Worker 不调用任何支付接口；`AUTO_REFUNDED` 仍仅表示模拟业务状态。
- 每一轮使用独立数据库会话，`finally` 中关闭；异常记录后下一轮可继续运行。

## 测试与验收

1. 先写失败测试：首次运行的任一来源失败、数量不足或价格区间缺失时，状态为 `INITIALIZATION_FAILED`，且没有发布商品。
2. 测试成功快照后再刷新失败时保留目录、状态为 `READY`，并保留可追溯的失败原因。
3. 测试 Worker 只请求 vivo、OPPO 固定来源，且不接受调用方 URL。
4. 电商 E2E 覆盖三角色登录定向、目录未就绪门禁、客户购买/退款、客服队列与客服/主管并发审批冲突。
5. `scripts/commerce_e2e.py` 在目录未就绪或为空时非零退出并输出明确失败原因；就绪时验证核心 HTTP 链路。
6. 运行后端相关测试、前端构建、Compose 构建和启动、`/healthz`。官网实时结果未达门槛时，报告“门禁按预期拒绝”，不将商城判定为可售。

## 非目标

- 不重做商城 UI 或新增商品来源。
- 不改变认证协议、已有角色、生产密钥或数据库迁移策略。
- 不在 API 请求链路中抓取网络商品。
