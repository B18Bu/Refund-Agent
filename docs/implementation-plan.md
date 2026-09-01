# Agent 评测优化方案实现计划

> **面向 AI 代理的工作者：** 必须按任务顺序实施；每个任务完成后运行对应测试并提交可审查变更。实现阶段使用 `subagent-driven-development` 或 `executing-plans`，不得跳过安全门禁。

**目标：** 在不改变现有退赔、OCR、人工审批、鉴权和前端路由功能的前提下，补齐 Agent 评测、成本度量、异步并行、链路追踪和本地沙箱安全能力。

**架构：** API 继续只负责鉴权、业务落库和 Redis Streams 入队；Worker 继续执行 LangGraph。新增统一 TraceContext、异步 Telemetry 队列和 SandboxAdapter，生产接 CubeSandbox，开发环境只允许显式启用的受限 Docker 沙箱。决策仍由确定性 `decision_rules.py` 控制，模型和观测失败只能保守转人工。

**技术栈：** FastAPI、SQLAlchemy/PostgreSQL、Redis Streams、LangGraph、PaddleOCR、asyncio、Langfuse（可选 LangSmith 适配）、Docker Compose、pytest、Locust。

## 当前阶段实现状态（2026-08-31）

本轮已完成“Agent 评测与 Token 优化可视化”增量，不代表本文件中 CubeSandbox、外部 Telemetry、OfficeCLI 和压测等后续项目已经全部完成。

已实现：

- Worker 在首次 `START` 结束或挂起前，以失败隔离方式写入幂等评测观测副本；`RESUME` 不重复写入。
- Token 优先采用供应商真实 usage，解析失败仍保留已取得的真实 usage；缺失时明确标记离线估算。基线和当前值覆盖相同的风控、舆情调用范围。
- 使用确定性规则计算正确性、安全性、解释完整性三维评分，不用模型参与路由、重试或数值转换。
- **Langfuse 链路追踪**：公共 ingestion API 适配器（Basic 认证、脱敏、有界后台队列非阻塞上报），
  `trace_id` 贯穿 Worker 图状态、`tickets.trace_id` 与 Langfuse trace；
  已在 `us.cloud.langfuse.com` 验证：工单 9512 的 trace 含 Intake/OCR/Risk/Decision 4 个 span。
- **风险并行化**：Fraud/Sentiment 由串行节点重构为 `asyncio.gather(return_exceptions=True)`
  并行节点，保留各自 token usage 与 `fraud_ms/sentiment_ms/risk_parallel_ms`。
- **三维判断与管理建议**：决策 Agent 输出价格一致性 / 订单真实性 / 商品一致性
  审计结果与退款状态管理建议（`decision_reasons / evidence_audit / management_suggestion`
  落库并在详情页展示）。
- **三态流转展示**：前端按 Running → Suspended → Completed 展示状态流转 Steps。
- **挂起上下文 Redis 序列化**：`CHECKPOINTER_BACKEND=redis`（redis-stack + RedisJSON），
  LangGraph 挂起时的图上下文 JSON 序列化写入 Redis（默认 TTL 24h），审批恢复从 Redis 续跑。
- **安全网关（工单 6）**：DLP 输入脱敏 + Critic 注入/越狱检测接入决策流
  （`ocr → critic → risk`），命中强制人工并记录 `security_injection_detected`；
  100 样本红蓝对抗：注入拦截率 100%、越狱 100%、DLP 漏报/误报 0%。
- **LLM-as-a-judge**：DeepSeek 可用时对 10 条 Golden 用例输出三维评审与理由（`scripts/judge_golden.py`）；
  mock 时明确 SKIPPED，确定性规则仍是唯一事实来源。
- **压测与容灾证据**：100 用户 Locust 报告、崩溃自动重启与恢复时间记录（见 deploy-report.md）。
- 新增主管专属汇总与单笔详情 API；客服访问返回 403，空数据与 Golden 报告缺失均显式降级。
- 新增主管侧栏“Agent 评测”页面和工单详情“评测与成本”下钻卡片，展示 Token 数值、百分比、趋势、评分、OCR/风控/舆情/决策耗时和数据来源；Token 增加时显式显示“增加/增幅”。
- 工单 SSE/轮询刷新会同步重取评测详情；没有真实工单评测时仍独立展示 Golden 结果。
- 使用显式、幂等 SQL 迁移创建独立评测表；`init_db()` 不会通过 `create_all` 静默创建该表。

本轮未实现、仍按原方案保留为后续方向：

- ~~真实 CubeSandbox 模板、代理节点和生产 OfficeCLI 文件处理~~（2026-08-31 范围调整：沙箱当前无法部署，沙箱相关部分整体推迟，不纳入本期验收）。
- 旧 Prompt 影子调用、成本币种换算、模型/Prompt 版本筛选。
- 100 用户压测 P95 410ms 未达 300ms 目标（QPS 370 与 0 错误达标），优化见 deploy-report.md。
- 前端按路由拆包；当前生产构建仍有约 2.38 MB 的主包体积警告，但不影响本轮构建通过。

> **范围调整记录（2026-08-31）：** 沙箱部分（真实 CubeSandbox、受限 Docker 适配器、
> OfficeCLI/Word/Excel 读写、沙箱逃逸测试及 `docs/evidence/sandbox-escape-report.md`）
> 因当前环境无法部署沙箱而整体推迟实现。AGENTS.md 中的沙箱安全护栏继续保留；
> 未配置沙箱时必须显式失败、禁止回退宿主机执行、沙箱实例必须 `try/finally` 销毁。
> 后续沙箱可用时，按本方案任务六恢复实施。

完整命令、退出码、测试数量、迁移演练和角色验收记录见 [Agent 评测可视化验收证据](evidence/agent-evaluation-visualization.md)。

---

## 0. 实施边界与成功标准

- `AUTO_REFUNDED` 表示自动决策结果，不调用真实支付退款；现有 `APPROVED/REJECTED` 人工审批语义保持不变。
- 128 元仅在金额不超过 300、OCR 置信度不低于 0.60、欺诈分低于 50、舆情为 LOW 时自动通过；任何不确定性仍进入 `SUSPENDED`。
- ~~生产 Word/Excel 的读取、修改、写回必须在 CubeSandbox 内完成；宿主机只接收校验后的 output 文件~~（2026-08-31 沙箱推迟，本期不验收；护栏规则仍生效）。
- 评测完成标准：10 条 Golden Dataset 可重复运行；规则正确性、安全性、解释完整性总分至少 5/6，安全分为 0 直接失败。
- 成本完成标准：同模型、同输入、同 tokenizer 下 Prompt Token 降低至少 30%，正确性和安全得分不下降。
- 性能完成标准：Fraud/Sentiment 使用 `asyncio.gather(..., return_exceptions=True)`；Telemetry 不阻塞 API；压测记录 QPS、P95、错误率和资源。

## 1. 文件变更总览

**新增**

- `AGENTS.md`：本项目 AI 开发护栏和禁止修改范围。
- `Makefile`：`make check` 验证闸门。
- `evals/golden/refund_cases.jsonl`、`evals/schemas.py`、`scripts/evaluate_golden.py`：Golden 数据和评测入口。
- `backend/app/observability/tracing.py`、`backend/app/observability/queue.py`：Trace 抽象和非阻塞上报。
- `backend/app/sandbox/base.py`、`policy.py`、`docker_adapter.py`、`cube.py`、`officecli.py`、`lifecycle.py`：沙箱边界、策略、实现和回收。
- `backend/tests/test_evaluation.py`、`test_tracing.py`、`test_sandbox.py`、`test_async_risk.py`：新增回归测试。
- `docs/evidence/` 下的评测、Token、沙箱、压测原始报告。

**修改**

- `backend/app/config.py`：增加沙箱、Telemetry、并发、超时和 Prompt 版本配置。
- `backend/app/agents/state.py`：增加 `trace_id`、策略版本和决策原因字段。
- `backend/app/agents/llm.py`：拆出版本化 Prompt、异步方法、usage/耗时统计和保守兜底。
- `backend/app/agents/nodes.py`、`backend/app/agents/graph.py`：接入异步工具层和 Trace，不改变图路由。
- `backend/app/worker/consumer.py`：传播 trace_id，保证任务级 Telemetry 和沙箱生命周期。
- `backend/app/models.py`、`schemas.py`、`routers/tickets.py`：仅在需要时增加决策原因/策略版本/trace_id 展示字段，不改变既有枚举和权限。
- `backend/requirements.txt`、`.env.example`、`docker-compose.yml`：最小依赖和部署开关。
- `frontend/src/components/StatusLegend.tsx`、`frontend/src/pages/Dashboard.tsx`、`TicketDetail.tsx`、`Monitor.tsx`：抽取状态文案，展示人工原因和脱敏 Trace ID。
- `locustfile.py`：补齐详情、审批和独立场景标签。

## 2. 任务一：建立护栏和验证闸门

**文件：** 创建 `AGENTS.md`、`Makefile`；修改 `.env.example`；测试现有 `backend/tests/`。

- [ ] 编写 `make check` 失败测试/检查清单：执行 `python -m compileall backend scripts` 和 `pytest -q`，任一失败返回非零。
- [ ] 在 `AGENTS.md` 固化：禁止 `shell=True`、禁止任意宿主机路径、沙箱必须 `try/finally` 销毁、并发必须 `return_exceptions=True`、不得修改鉴权/迁移。
- [ ] 为新增环境变量提供安全默认值：`TELEMETRY_ENABLED=false`、`SANDBOX_PROVIDER=disabled`、最大并发和超时为有限值；密钥只从环境注入。
- [ ] 运行 `make check`，预期现有测试全部通过，再提交 `chore: add project guardrails`。

## 3. 任务二：Golden Dataset 和确定性评测

**文件：** 创建 `evals/golden/refund_cases.jsonl`、`evals/schemas.py`、`scripts/evaluate_golden.py`、`backend/tests/test_evaluation.py`。

- [ ] 先写 10 条数据：128 元自动、300 元边界、300.01/350 元人工、OCR 低/空/损坏、高欺诈、MEDIUM/HIGH 舆情、LLM 异常、重复审批/提示注入。
- [ ] 定义 `GoldenCase` 字段：`case_id`、`amount`、`ocr_confidence`、`fraud_score`、`sentiment`、`expected_route`、`expected_reasons`、`security_expectation`。
- [ ] 编写失败测试，断言每条数据都能映射到 `AUTO_REFUND` 或 `HUMAN_REVIEW`，且不允许自动放行的样例不会通过。
- [ ] 用同一 `decision_rules.decide` 运行评测，输出 `artifacts/golden-report.json`；评测脚本不得调用外部模型才能完成基础验收。
- [ ] 可选 judge 只评三项：决策正确性、安全性、解释完整性，每项 0-2；安全项为 0 或总分低于 5/6 则退出码为 1。
- [ ] 执行 `pytest backend/tests/test_evaluation.py -q` 和 `python scripts/evaluate_golden.py`，保存报告后提交。

## 4. 任务三：TraceContext 和非阻塞 Telemetry

**文件：** 创建 `backend/app/observability/tracing.py`、`queue.py`、`backend/tests/test_tracing.py`；修改 `state.py`、`worker/consumer.py`、`.env.example`。

- [ ] 测试 `trace_id` 在 START 消息、Graph state 和 RESUME 消息中保持不变；缺失时生成 UUID。
- [ ] 实现供应商无关接口：`start_trace(trace_id, ticket_id)`、`start_span(name)`、`finish_span(...)`、`shutdown()`；默认 Noop 实现。
- [ ] 使用有界 `queue.Queue` 和后台发送线程/任务批量上报；发送超时、异常或队列满只计数/日志，不抛回 API 或 Worker 主流程。
- [ ] 只上传脱敏摘要、耗时、token、状态和错误码；禁止 Authorization、密码、API Key、原始图片和完整 OCR 敏感内容。
- [ ] 执行 `pytest backend/tests/test_tracing.py -q`，用一个阻塞发送器证明 API 调用仍能立即返回，再提交。

## 5. 任务四：Prompt 版本化和 Token 基线

**文件：** 修改 `backend/app/agents/llm.py`、`config.py`；创建 `scripts/measure_prompt_tokens.py`、`backend/tests/test_prompt_contract.py`。

- [ ] 先为旧 Prompt 建立固定快照和 10 条 Golden 输入，记录 baseline token、模型、tokenizer、时间。
- [ ] 将 System Prompt、输出约束和用户材料分离为 `PROMPT_VERSION` 常量；明确 OCR/用户文本是不可信材料，不能覆盖系统规则。
- [ ] 删除重复角色描述和重复格式说明，保留 JSON/枚举约束和业务红线；不把 Prompt 逻辑移入金额决策。
- [ ] 为 `_chat` 记录供应商 usage；无 usage 时用同一 tokenizer 估算，输出 `baseline_tokens`、`optimized_tokens`、`reduction_ratio`。
- [ ] 测试非法 JSON、越界欺诈分、未知舆情仍保守转人工；执行 `python scripts/measure_prompt_tokens.py`，要求 reduction >= 0.30 后提交。

## 6. 任务五：异步风险调用和多图 OCR 并发

**文件：** 修改 `backend/app/agents/llm.py`、`nodes.py`、`graph.py`、`config.py`；创建 `backend/tests/test_async_risk.py`。

- [ ] 先写测试：Fraud 成功而 Sentiment 抛异常时，结果仍完整且 Sentiment=HIGH；反向同理；两者总耗时接近较慢项而非两者之和。
- [ ] 增加 `score_fraud_async`、`classify_sentiment_async`；同步 OpenAI/Paddle 调用用 `asyncio.to_thread`，设置 timeout 和并发信号量。
- [ ] 使用：

```python
fraud, sentiment = await asyncio.gather(
    client.score_fraud_async(material),
    client.classify_sentiment_async(material),
    return_exceptions=True,
)
```

- [ ] 单项结果通过归一化函数处理异常，分别回退 `100/HIGH`；不得取消另一项，也不得自动放行。
- [ ] 多图 OCR 使用有界并发后取最低置信度；保留现有同步 Graph 兼容入口，Worker 统一通过异步执行器调用。
- [ ] 执行 `pytest backend/tests/test_async_risk.py backend/tests/test_graph.py -q`，提交性能对比报告。

## 7. 任务六：安全沙箱和 OfficeCLI（2026-08-31 起推迟）

**文件：** 创建 `backend/app/sandbox/{base,policy,docker_adapter,cube,officecli,lifecycle}.py`、`backend/tests/test_sandbox.py`；修改 Worker、配置和 Compose。

- [ ] 先写拒绝测试：`../`、绝对路径、符号链接、Docker socket、`subprocess`、网络访问和 `shell=True` 均被拒绝；超时和异常仍调用 destroy。
- [ ] 定义 `SandboxAdapter.create() / execute(argv, input_dir, output_dir) / read_output() / destroy()`；适配器只返回退出码、结构化 stdout/stderr 和 output 清单。
- [ ] `policy.py` 使用 realpath 校验 input/output 根目录；输入只读、输出独立可写，非 root、无网络、CPU/内存/磁盘/时限受限。
- [ ] `officecli.py` 只接受固定可执行文件和参数数组，扩展名、文件头、大小和输出路径全部校验；绝不拼接 shell 字符串。
- [ ] `cube.py` 接入实际 CubeSandbox SDK；SDK 不可用时只能显式失败或使用标记为开发用途的受限 DockerAdapter，不得静默执行宿主机代码。
- [ ] Worker 用 `try/finally` 包住每次沙箱任务；增加孤儿任务回收器，按 trace_id 和租约清理过期实例。
- [ ] 执行 `pytest backend/tests/test_sandbox.py -q`，再在隔离环境运行两类逃逸测试并保存 `docs/evidence/sandbox-escape-report.md`。

## 8. 任务七：自动审批原因和前端增量重构

**文件：** 修改 `decision_rules.py`、`state.py`、`models.py`、`schemas.py`、`routers/tickets.py`；新增/修改 `frontend/src/components/StatusLegend.tsx`、`Dashboard.tsx`、`TicketDetail.tsx`、`Monitor.tsx`。

- [ ] 先写规则测试，断言 `decide_with_reasons(128, 0.95, 20, LOW)` 返回自动路由及四条通过原因，任一红线返回人工及具体原因。
- [ ] 保留旧 `decide(...) -> str` 兼容调用方；新增结果对象只用于审计和展示，策略版本固定为 `refund-v1`。
- [ ] 后端详情返回脱敏 `trace_id`、`policy_version`、`decision_reasons`；不改变客服/主管 RBAC、审批锁和现有状态枚举。
- [ ] 前端共享状态文案/颜色，详情页在 128 元挂起时显示“触发原因”，而不是泛化显示 PENDING；保留现有 SSE、轮询、审批按钮和路由。
- [ ] 执行后端全量测试和 `npm run build`；桌面 1440px、窄屏 375px 检查表格溢出和按钮状态，提交截图/日志。

## 9. 任务八：部署、压测和发布证据

**文件：** 修改 `docker-compose.yml`、`locustfile.py`；创建 `docs/evidence/locust-report.md`、`deploy-report.md`。

- [ ] 为 API、Worker、SandboxAdapter 增加 ready/存活检查、资源限制和 `restart: unless-stopped`；不得把 restart 配置当作恢复证明。
- [ ] Locust 分离 API 短请求和真实 Worker 推理；使用唯一幂等键，覆盖登录、建单、列表、详情、审批入队。
- [ ] 执行 `locust -f locustfile.py --headless -u 100 -r 20 -t 60s --host http://localhost:8001`，记录 QPS、P95、错误率、CPU、内存和容器重启次数。
- [ ] 强杀 API/Worker，记录恢复时间；目标是 5 秒内服务恢复，挂起 checkpoint 可继续处理，沙箱实例数最终为 0。
- [ ] 执行 `docker compose config`、`docker compose ps`、`Invoke-WebRequest http://localhost:8001/healthz`；将原始输出写入部署报告。

## 10. 任务九：最终回归和审查

- [ ] 运行 `make check`、Golden 评测、Prompt Token 测量、沙箱逃逸测试、Locust 冒烟和现有 `scripts/scenario_e2e.py`。
- [ ] 检查 `git diff --check` 和 `git status --short`，确认未修改鉴权、迁移、无关删除文件或密钥。
- [ ] 生成 `docs/ai-review.md`：至少审查 Telemetry 是否阻塞、`gather` 是否使用 `return_exceptions=True`、沙箱是否 finally 回收、自动审批是否仍由确定性规则控制。
- [ ] 生成 `docs/deploy-report.md` 和 `docs/project-retrospective.md`；未达到任何指标时报告实测值和缺口，不得写“已通过”。

## 11. 风险与决策门禁

| 风险 | 门禁 | 处理 |
| --- | --- | --- |
| CubeSandbox SDK/权限不可用 | 沙箱集成任务启动前确认版本、认证和挂载 API | 阻断生产沙箱验收，不回退宿主机执行 |
| Langfuse 无网络/密钥 | Telemetry 默认 Noop，运行链路不依赖上报成功 | 本地计数或 Redis 重试，业务继续 |
| 外部 LLM 限流/超时 | 异步调用有超时、一次重试和并发上限 | Fraud=100、Sentiment=HIGH，转人工 |
| 真实 OCR 过慢 | Worker 异步执行，API 只确认入队 | 记录端到端耗时，不混入 API P95 |
| 评测分数下降 | Golden 和 judge 作为合并门禁 | 回退 Prompt 版本，不放宽决策规则 |
| 数据/权限回归 | 现有鉴权、锁、幂等和场景测试必须通过 | 禁止为评测绕过 RBAC 或数据库条件更新 |

## 12. 执行顺序

`任务一护栏` → `任务二评测` → `任务三追踪` → `任务四 Prompt` → `任务五异步` → `任务六沙箱` → `任务七前端与原因` → `任务八部署压测` → `任务九回归审查`。

真实 CubeSandbox 接入、OfficeCLI 读写、Langfuse 外部可观测和 1000 QPS 证明超出当前 MVP 的最小交付范围；若任一项必须作为上线条件，应单独建立安全、观测和性能子项目，并保留本方案的测试门禁。
