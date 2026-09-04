# Quickstart Validation: 多 Agent 协同客诉舆情退赔决策系统（MVP）

> 验证指南：证明功能端到端可用。实现细节见 `tasks.md` 与实现阶段；接口契约见 [contracts/api.md](./contracts/api.md)；
> 数据模型见 [data-model.md](./data-model.md)。

## 前置条件

- Docker 与 Docker Compose。
- 可访问的 DeepSeek（OpenAI 兼容）API Key（经环境变量注入，见 `.env`）。
- 预置演示账号：至少 1 名客服 + 1 名主管（生产经初始化脚本/管理员创建）。

## 一键启动

```bash
# 在仓库根目录
cp .env.example .env        # 填入 JWT_SECRET、DB 密码、LLM Key
docker compose up -d --build
docker compose ps           # 五服务均 healthy
```

健康检查：`GET /healthz`（API 存活）、`GET /readyz`（DB/Redis 就绪）。

## 端到端验证场景（E2E-01 ~ E2E-08）

> 通过 API 或大屏操作，逐条核验预期结果。

| 编号 | 场景 | 预期结果 |
| --- | --- | --- |
| E2E-01 | 提交 350 元 + 清晰凭证 + 低风险 | 工单进入「待人工审批」；主管批准后进入「已完成·已批准」 |
| E2E-02 | 提交 128 元 + OCR≥0.60 + 风险 20 + 舆情低 | 直接「已完成·自动退赔」，无人工干预 |
| E2E-03 | OCR 置信度过低 | 强制「待人工审批」 |
| E2E-04 | 相同幂等键重复/并发建单 | 返回同一工单，数据库仅一条 |
| E2E-05 | 两名主管并发审批同一挂起工单 | 仅一条审批有效，另一条 `409` |
| E2E-06 | 客服审批 / 越权读他人单 | 返回 `403` 或安全 `404` |
| E2E-07 | LLM 超时 / 格式错误 | 不自动通过，保守进入人工审批 |
| E2E-08 | 强杀 API / Worker 容器 | 5 秒内按容器策略恢复；未完成消息可续处理或被标记失败 |

## 验证脚本示例

```bash
# 1. 登录拿 token（演示账号见 README「演示账号」，密码统一 secret123）
curl -s -X POST http://localhost:8001/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"supervisor_01","password":"secret123"}'

# 2. 建单（携带幂等键；image_paths 为服务端已存凭证路径，可先上传后填）
curl -s -X POST http://localhost:8001/api/tickets \
  -H "Authorization: Bearer <token>" \
  -H "X-Idempotency-Key: $(uuidgen)" \
  -H 'Content-Type: application/json' \
  -d '{"amount":"350.00","image_paths":[]}'

# 3. 上传凭证
curl -s -X POST http://localhost:8001/api/tickets/<ticket_id>/files \
  -H "Authorization: Bearer <token>" \
  -F "files=@invoice.jpg"

# 4. 主管审批（路径为 /approval，同 <ticket_id> 的挂起工单）
curl -s -X POST http://localhost:8001/api/tickets/<ticket_id>/approval \
  -H "Authorization: Bearer <supervisor-token>" \
  -H 'Content-Type: application/json' \
  -d '{"action":"APPROVE","comment":"情况属实，批准退款"}'
```

## 压测冒烟（Locust）

```bash
# 压测对象为短时核心 API（登录/建单/列表/详情/审批入队），非云端 LLM 完整时长
pip install locust
locust -f locustfile.py --headless -u 200 -r 20 --run-time 60s --host http://localhost:8001
```

验收基线：QPS ≥ 200、P95 < 300ms、错误率 < 0.1%；报告记录宿主机资源与原始输出，
并区分「API 性能」与「真实 AI 推理时延」。

## 期望的最终状态

- 低风险工单自动得到「自动退赔」结论。
- 高风险/不确定工单 100% 进入人工审批，绝不错误自动放行。
- 任一工单决策过程可完整追溯（环节轨迹、审批人、审批意见、失败原因）。
# 电商演示入口

- 游客访问 `/shop` 浏览商品；登录后可在侧栏进入购物车、订单和退单。
- 支付为模拟支付：不会采集银行卡、支付密码或调用真实支付接口。
- 应用内端到端验收：`.venv\\Scripts\\python.exe -m pytest backend/tests/test_commerce_e2e.py -q`
- 已启动服务时可检查商品目录：`.venv\\Scripts\\python.exe scripts/commerce_e2e.py http://localhost:8001`
