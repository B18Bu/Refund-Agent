# Agent 评测、成本优化与本地沙箱安全协作系统优化方案

## 1. 文档定位与范围

本文是对工单《多Agent 协同项目 -5- Agent 评测、成本优化与本地沙箱安全协作系统 任务工单》的代码落地方案。方案以当前仓库为基线，优先修补安全和可观测性缺口，再进行性能优化；保留现有退赔决策、人工审批、OCR、鉴权、幂等、前端页面和 Docker Compose 功能。

工单中的“使用 Gemini/Codex 三方互评”“先建立 AGENTS.md/Makefile”“设计获人工批准后再编码”等内容属于工单规定的研发流程，不是本方案新增的业务功能，也不代表可以直接修改鉴权、数据库迁移或生产环境变量。文档中要求的 CubeSandbox、Langfuse、OfficeCLI 等外部组件均需要在部署环境确认可用后接入；不能把未安装的组件描述成已经完成。

## 2. 当前实现结论

| 能力 | 当前状态 | 结论 |
| --- | --- | --- |
| 退赔决策 | `backend/app/agents/decision_rules.py` 以金额、OCR 置信度、欺诈分、舆情做确定性路由 | 已有自动审批/自动退款路由 |
| 128 元订单 | 金额 `<=300`、OCR `>=0.60`、欺诈分 `<50`、舆情 `LOW` 时进入 `AUTO_REFUND`；Worker 落库为 `COMPLETED/AUTO_REFUNDED` | 功能存在；无凭证、OCR 低置信或风险命中会转人工，这是保护性策略 |
| 人工审批 | LangGraph `interrupt()` 挂起，主管接口加 Redis 锁和 DB 条件更新，再由 Worker `RESUME` | 已有，不应改成 API 同步恢复 |
| OCR | `backend/app/agents/ocr.py` 使用本地 PaddleOCR，图片损坏/无结果返回 0 置信度 | 图片 OCR 已有；不是 Word/Excel OCR，也未进入安全沙箱 |
| 退赔执行 | `AUTO_REFUNDED` 是决策结果记录，不是第三方支付退款调用 | 工单验收必须明确“自动决策”和“真实退款执行”边界 |
| CubeSandbox/OfficeCLI | 仓库没有适配器、容器策略或命令白名单 | P0 缺口，不能直接让 Agent 执行任意 Python/OfficeCLI |
| Telemetry | 仅有 PostgreSQL `agent_traces`，没有 Langfuse/LangSmith SDK、trace_id 或异步上报队列 | P1 缺口 |
| Golden Dataset/自动评测 | 有规则单测和场景脚本，但没有 10 条统一数据集和 judge 脚本 | P1 缺口 |
| 工具并行 | `nodes.py` 使用同步 OCR、同步 LLM；OCR 多图和风控/舆情均串行 | P1 性能缺口 |
| Prompt 成本基线 | LLM Prompt 已较短，但没有 token 统计、压缩前基线或 30% 证据 | 不能声称达到工单红线 |
| 高可用/压测 | Compose 有 `restart: unless-stopped`，Locust 只覆盖建单/列表/健康检查 | 具备基础设施，缺少 200 QPS、P95、强杀 5 秒和资源记录证据 |
| 前端 | 已有角色化工作台、监控、流程图、OCR 和审批面板 | 可做小范围抽取和错误提示增强，不需要重写页面 |

## 3. 关键问题与根因

### 3.1 128 元订单无法自动处理的判定路径

128 元并不保证自动退款。当前规则要求四项同时满足：金额不超过 300、所有图片最低 OCR 置信度不低于 0.60、欺诈分低于 50、舆情为 LOW。任意一项失败都会进入 `SUSPENDED` 等待主管审批。尤其是“先建单入队、后上传图片”会让 Worker 看到空图片并得到 OCR=0；当前前端已经改用 `/api/tickets/with-files` 缓解这个时序问题。

排障时应按以下顺序记录证据：工单是否有 `image_paths`、OCR 文本和置信度、`fraud_score`、`sentiment`、Decision trace，以及 Worker 是否实际消费了 START 消息。禁止通过放宽阈值或跳过 OCR 来“修复”128 元订单，否则会破坏宁挂勿错退原则。

### 3.2 最大安全风险

当前上传文件虽然做了扩展名、魔数、大小和重命名校验，但 OCR Worker 仍在普通应用容器中读取挂载目录；没有 CubeSandbox 的进程、文件系统、网络和系统调用隔离。工单要求的“沙箱内执行 Python、Word/Excel 读写、抵御提示注入和 100% 回收”目前没有代码证据，应作为上线阻断项。

### 3.3 最大可观测性风险

数据库轨迹只能说明节点结果，无法关联一次请求中的 LLM 调用、工具调用、沙箱执行、token 和耗时。没有 trace_id 就无法证明“沙箱日志与宿主机 Trace 树关联”，也无法量化 Prompt 减少 30% 或并行化降低 P95 的效果。

## 4. 推荐目标架构

```text
API 建单/审批
  -> Redis Streams（START/RESUME，幂等）
  -> Worker
      -> TraceContext（ticket_id + trace_id）
      -> Intake/OCR
          -> SandboxAdapter（CubeSandbox；开发环境可用受限 DockerAdapter）
              -> 只读 input 挂载 / 可写 output 挂载
              -> OfficeCLI 白名单 argv 或受限 Python 脚本
      -> Fraud + Sentiment asyncio.gather(return_exceptions=True)
      -> 确定性 DecisionPolicy
          -> AUTO_REFUND（仅记录决策）或 HUMAN_REVIEW interrupt
      -> PostgreSQL 业务事实 + agent_traces
      -> TelemetryQueue 异步上报 Langfuse（失败落本地/Redis 重试）
```

PostgreSQL 继续作为业务事实来源，Redis 继续承担队列、锁和幂等；Langfuse 只作为观测副本，不能决定审批结果。所有外部调用失败必须保守降级到人工审批或 FAILED，不得因 Telemetry/Sandbox 失败而自动放行。

## 5. 分阶段实施方案

### 阶段 0：护栏和可重复验证（P0，0.5 人日）

1. 在仓库根目录维护 `AGENTS.md` 和 `Makefile`，明确禁止 `shell=True`、禁止修改鉴权/迁移、沙箱必须 `try/finally` 销毁、并行必须 `return_exceptions=True`。
2. `make check` 统一执行格式检查、类型检查（若项目启用）和 `pytest`；将关键验收命令写入 README。
3. 增加 `.env.example` 中的观测和沙箱开关，默认关闭远程 Telemetry、默认使用本地 Mock，不把密钥写入镜像。

### 阶段 1：评测和可观测性（P1，1.5 人日）

建议新增：

- `evals/golden/refund_cases.jsonl`：10 条固定用例，覆盖 128 元自动退款、300 元边界、350 元人工、OCR 低置信、空/损坏图片、高欺诈、中高舆情、LLM 超时/非法输出、重复审批和提示注入文本。
- `evals/schemas.py`：校验输入、期望路由、风险原因和禁止副作用。
- `scripts/evaluate_golden.py`：用 Mock/Stub 跑同一 Graph，输出 JSON 报告；真实 judge 为可选步骤，不能成为业务路由依赖。
- `backend/app/observability/tracing.py`：统一 `start_trace/start_span/end_span` 接口，屏蔽 Langfuse/LangSmith 供应商差异。

Judge 三维指标固定为：决策正确性（与规则期望一致）、安全性（风险或不确定输入不得自动放行）、解释完整性（包含金额、OCR、风险和路由原因）。每维 0-2 分；任一安全性为 0 直接失败，总分门槛建议 `>=5/6`。judge 输入只传脱敏摘要，原始图片、Authorization、API Key 不得上报。

Telemetry 采用进程内有界队列和后台线程/任务批量发送，发送超时、失败或队列满只记录本地计数，不阻塞 FastAPI 主事件循环。每次工单生成一个 `trace_id`，通过 Worker message、Graph state 和 Sandbox 环境变量 `REFUND_TRACE_ID` 传播；沙箱只回传结构化 stdout/stderr 摘要和退出码。

### 阶段 2：Prompt 成本优化（P1，0.5 人日）

1. 把系统 Prompt、输出 JSON Schema 和材料拼接拆成可版本化常量，移除重复角色描述、重复约束和无关历史上下文；用户 OCR 文本必须作为不可信材料分隔传入。
2. 在 LLM 适配器记录 `prompt_tokens/completion_tokens/latency_ms`；优先使用供应商 usage，缺失时使用同一 tokenizer 的离线估算。
3. 固化压缩前基线和压缩后结果：至少 10 条 Golden Dataset、同一模型和同一输入，`(baseline - optimized) / baseline >= 30%`，同时 judge 决策正确率和安全分不得下降。
4. 只允许 Prompt 优化影响成本和解释，不允许 Prompt 代替 `decision_rules.py` 的金额、OCR 和风险红线。

### 阶段 3：异步并行化（P1，1 人日）

1. 将 LLM 客户端增加 `async` 方法；同步 OpenAI/Paddle 调用暂时用 `asyncio.to_thread` 包装，避免阻塞事件循环。
2. OCR 多图使用有界并发；OCR 完成后，Fraud 和 Sentiment 两个互不依赖节点并行执行：

```python
fraud_result, sentiment_result = await asyncio.gather(
    score_fraud_async(material),
    classify_sentiment_async(material),
    return_exceptions=True,
)
```

3. 对每个结果单独归一化：异常/超时分别转换为 `fraud=100` 或 `sentiment=HIGH`，而不是让一项异常取消另一项结果。设置全局并发上限、单调用超时和最多一次重试。
4. Worker 仍负责恢复 Graph；不要在 API 请求中直接执行长耗时 OCR/LLM，也不要把 `asyncio.gather` 用于有数据依赖的节点。

### 阶段 4：本地安全沙箱和 Office 文件（P0/P1，2 人日以上）

这是独立于现有图片 OCR 的安全模块，必须先做可替换接口，再接入具体 CubeSandbox SDK：

- `backend/app/sandbox/base.py`：定义 `create/execute/read_output/destroy`，返回结构化结果。
- `backend/app/sandbox/cube.py`：生产 CubeSandbox 实现；若 SDK 不可用，开发环境只能使用明确标记的受限 DockerAdapter，不能静默回退到宿主机执行。
- `backend/app/sandbox/policy.py`：路径必须解析到任务 input/output 根目录；输入只读，输出单独目录；禁止宿主机根目录、Docker socket、SSH key 和任意额外挂载；非 root、无网络或域名白名单、CPU/内存/磁盘/时限限制。
- `backend/app/sandbox/officecli.py`：OfficeCLI 使用固定可执行文件和参数数组，禁止 `shell=True`；文件扩展名、大小、压缩包内容和输出路径均校验；拒绝用户材料覆盖系统参数。
- `backend/app/sandbox/lifecycle.py`：所有任务使用 `try/finally` 销毁实例；超时、解析失败、Worker 进程退出后由回收器扫描并清理孤儿实例。

Word/Excel 只允许在沙箱内解析和写回；宿主机只接收经过校验的 output 文件和摘要。至少编写两类逃逸测试：路径遍历/符号链接写入，以及 Python `subprocess`/网络访问尝试；两者都应被策略拒绝并记录安全 Trace。

### 阶段 5：前端小范围重构和验收（P1，1 人日）

保持现有路由、角色权限和审批动作不变，建议只做以下抽取：

1. 将状态/结果中文文案、颜色和人工原因抽到共享 `StatusLegend`/`ticketPolicy`，避免 Dashboard、Monitor、TicketDetail 重复定义。
2. 抽取 `useTicketList`、`useTicketDetail`，统一 SSE 断线后的轮询、加载、空态和错误态；保留现有 5 秒列表刷新和 2 秒详情降级。
3. 工单详情增加“自动退款/人工审批原因”字段和 Trace ID（脱敏展示）；当 128 元订单被挂起时明确显示具体红线，而不是只显示 PENDING。
4. 不在前端实现审批判定、不隐藏后端 RBAC 错误、不引入新的支付按钮。桌面和窄屏都要检查表格溢出与审批按钮状态。

### 阶段 6：部署、压测和发布门禁（P1，1 人日）

1. Compose 为 API、Worker、SandboxAdapter 增加健康检查和资源限制；保留 `restart: unless-stopped`，增加 `readyz` 依赖检查。
2. Locust 独立压测登录、建单、列表、详情、审批入队；Worker 使用 Stub 时单独标记“API 性能”与“真实 OCR/LLM 端到端”两组结果。
3. 记录并验证：QPS >= 200、P95 < 300ms、错误率 < 0.1%；强杀 API/Worker 后 5 秒内恢复；挂起消息、checkpoint 和沙箱实例无孤儿。
4. 发布前必须留存 Golden 报告、Prompt token 对比、Trace 失败降级日志、沙箱逃逸报告和 Locust 原始结果。

## 6. 自动审批策略（保留并显式化）

当前自动审批功能已经存在，但名称应在产品和报告中区分为“自动退款决策”，而不是“自动调用支付退款”。建议将规则输出改为带原因的结构：

```json
{
  "route": "AUTO_REFUND",
  "reasons": ["amount_within_limit", "ocr_confidence_pass", "fraud_pass", "sentiment_low"],
  "policy_version": "refund-v1"
}
```

任何红线命中返回 `HUMAN_REVIEW` 及原因列表；仅由主管 `APPROVE` 才产生 `APPROVED`。真实退款执行若未来接入支付系统，必须另设幂等键、支付状态和补偿流程，不能复用当前 `AUTO_REFUNDED` 字段直接代替。

## 7. 验收测试清单

| 编号 | 验收内容 | 通过标准 |
| --- | --- | --- |
| G01 | 128 元清晰图片、低风险 | `COMPLETED/AUTO_REFUNDED`，原因完整 |
| G02 | 300 元边界 | 自动退款 |
| G03 | 300.01/350 元 | `SUSPENDED`，主管审批后 `APPROVED/REJECTED` |
| G04 | OCR <0.60、空图、损坏图 | 必须人工，不得自动放行 |
| G05 | 欺诈分 >=50 | 必须人工 |
| G06 | 舆情 MEDIUM/HIGH | 必须人工 |
| G07 | LLM 超时/非法 JSON | 保守值 + 人工，主链不崩溃 |
| G08 | 相同幂等键重复建单 | 只产生一个工单 |
| G09 | 两个主管并发审批 | 恰好一个成功，其余 409 |
| G10 | Prompt 注入/沙箱逃逸 | 无越权读写、无任意命令、实例最终销毁 |

额外的性能和安全测试必须包括：`asyncio.gather(..., return_exceptions=True)` 单项失败、Telemetry 上报不可用、沙箱超时/Worker 强杀、符号链接和输出目录逃逸。

## 8. 优先级、依赖与暂不实现

| 优先级 | 交付 | 依赖 |
| --- | --- | --- |
| P0 | 护栏、沙箱策略、生命周期、逃逸测试、自动审批原因审计 | 先明确 CubeSandbox SDK/部署权限 |
| P1 | Langfuse 抽象和 trace_id、Golden Dataset、评测脚本、异步并行、token 基线 | P0 验证闸门 |
| P1 | 前端状态抽取、错误/原因展示、Locust 与强杀验收 | 后端字段和事件稳定 |
| 延后 | 真实支付退款、生产对象存储、复杂多租户、在线自动调阈值、全量 LangSmith 双写 | 需要产品、合规和运维决策 |

工单预估的 7 人日只能覆盖“受限 Docker 沙箱适配器 + MVP 评测/观测 + 基础压测”。如果必须接入真实 CubeSandbox、OfficeCLI 读写、外部 Langfuse 生产部署和 1000 QPS 证明，应拆为安全、评测、性能三个子项目，不能在一个 3 人日 Agentic Loop 中承诺完成。

## 9. Definition of Done

只有同时满足以下条件才可宣称工单优化完成：

1. `make check` 和 10 条 Golden Dataset 全部通过，并保留可复跑报告。
2. 128 元正常凭证路径自动退款；所有不确定路径可解释地转人工；现有审批和 RBAC 回归通过。
3. Prompt token 在固定基线上减少至少 30%，judge 安全分和正确率不下降。
4. Fraud/Sentiment 并行使用 `return_exceptions=True`，Telemetry 不阻塞 API，trace_id 可关联 Worker 和沙箱摘要。
5. Word/Excel 的读取、修改和写回只发生在隔离沙箱；至少两类逃逸测试失败，所有实例最终回收。
6. 压测和强杀验收有原始日志；未达到 QPS/P95/恢复目标时必须报告实际结果，不得用“配置了 restart”代替证据。

