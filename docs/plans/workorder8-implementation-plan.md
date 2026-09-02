# 编排、意图与自动化测试系统——实施计划

> **面向 AI 代理的工作者：** 按任务顺序实施；每个任务完成后运行对应测试并提交可审查变更。
> 实现阶段使用 `subagent-driven-development` 或 `executing-plans`，不得跳过测试门禁。
> 本计划对应方案文档 `docs/workorder8-intent-orchestration-testing-plan.md` 与工单 8。

**Goal:** 在现有客诉舆情退赔决策系统上落地“确定性规则 + LLM”双层意图识别、显式异常兜底与死信队列、以及可定时触发的自动化评测框架，并验证混合流相对纯 LLM 的 Token 成本优势。

**Architecture:** 复用现有 LangGraph 决策流：新增 `intent` 节点（Node A 静态规则过滤/分流）与 `fallback` 节点（Node B 解析失败的显式兜底）；新增 `evaluation.runner` 一键评测与 `scripts/run_ab_benchmark.py` 成本对比；Worker 异常经 Redis Streams 原生 pending 语义落到 `stream:tickets:dead` 死信队列。

**Tech Stack:** LangGraph + Redis Streams/RedisJSON + DeepSeek（OpenAI 兼容客户端）+ PaddleOCR + Langfuse（ingestion REST）+ pytest。

**Spec:** `docs/workorder8-intent-orchestration-testing-plan.md`

## Global Constraints

- 简体中文对话/文档；代码标识符英文；注释与面向用户文案中文；全部 UTF-8。
- Node A 只做“过滤/分流”，不改变 `decision_rules.decide` 的确定性路由语义；
  `AUTO_REFUNDED` 仍仅为决策记录，不调用真实支付。
- 禁止 `shell=True`；命令必须是固定可执行文件加参数数组。
- 不修改鉴权协议、现有角色、审批锁、幂等键、数据库迁移策略与生产密钥；
  新增配置全部走 `backend/app/config.py`（可被环境变量覆盖）。
- 沙箱维持推迟；本计划不依赖沙箱，不得回退宿主执行。
- 失败必须显式暴露：任何跳过测试/样本的“通过”声明均为错误。

## 0. 实施边界与成功标准

- 双层意图识别只作用于 `risk` 阶段的上游分流：命中强信号（黑产/刷单/恶意关键词）
  时跳过 LLM、直接使用确定性欺诈分；未命中时走现有 LLM 并行分析，行为不降级。
- LLM 输出解析失败或调用失败：显式记录 `llm_output_parse_fallback` /
  `llm_call_failed` 到 `fallback_reasons` 与 `decision_reasons`，保守兜底转人工，绝不静默。
- LLM 网络故障：指数退避重试（首次 + 最多 2 次重试，退避 1s/2s），仍失败保守兜底；
  Worker 不可恢复异常 XADD 到 `stream:tickets:dead`（含 trace_id、error_code、原因）。
- 成功标准：
  - 新增意图/评测测试全过，后端全量 pytest 无回归；
  - 意图样本 ≥100 条；自动化覆盖率 100%；意图召回率 ≥90%；幻觉率 ≤2%；
  - A/B 对比：混合流相对纯 LLM 的 Token 消耗降低 ≥40%；
  - Golden 10/10、前端构建通过、兜底审计报告覆盖 4 类异常场景。

## 1. 文件变更总览

**新增**

- `docs/workorder8-intent-orchestration-tech-spec.md`：双层意图识别与自动化测试设计说明书。
- `docs/workorder8-three-party-alignment.md`：三方需求互评与测试策略记录。
- `backend/app/agents/intent.py`：Node A 确定性意图过滤（关键词 Trie/正则树 + 分流）。
- `backend/app/evaluation/runner.py`：一键周期评测（Golden + 安全网关 + 意图样本）与指标报告。
- `backend/tests/test_intent_filter.py`：Node A 分流测试。
- `backend/tests/test_eval_pipeline.py`：30 条口语意图样本 + Fallback/重试/评测指标/DLQ 测试。
- `evals/intent/intent_samples.jsonl`：≥100 条复杂口语意图样本（含标注）。
- `scripts/run_ab_benchmark.py`：纯 LLM vs 双层混合流 A/B 对比。
- `scripts/schedule_periodic_eval.py`：周期评测调度（Windows 计划任务 / 容器 cron）。
- `docs/evidence/periodic-eval-report.md`：周期评测报告（由 runner 生成）。
- `docs/evidence/ab-benchmark-report.md`：A/B 成本对比报告（由脚本生成）。
- `docs/evidence/fallback-audit-report.md`：异常兜底机制审计报告。
- `docs/interview-qa-workorder8.md`：《智能体编排与周期性测试面试 QA 知识库》。

**修改**

- `backend/app/config.py`：LLM 重试、DLQ、意图过滤开关与阈值。
- `backend/app/agents/state.py`：`intent_route`、`intent_label`、`intent_hit_rules`、`fallback_reasons`。
- `backend/app/agents/nodes.py`：新增 `intent_node` / `fallback_node`；`risk_node` 接入 fallback 原因。
- `backend/app/agents/graph.py`：`critic → intent` 分流、`risk → fallback → decision` 条件边。
- `backend/app/agents/llm.py`：解析失败显式原因 + 指数退避重试。
- `backend/app/worker/consumer.py`：`_NODE_DISPLAY` 增加 intent/fallback；异常 XADD 死信队列。
- `frontend/src/components/FlowCanvas.tsx`：节点列表增加“意图识别”与“异常兜底”。
- `frontend/src/pages/TicketDetail.tsx`：详情展示意图分流与兜底原因（如已有安全标签则同区域扩展）。

## 2. 任务一：意图分流规格与三方对齐（0.5 人日）

**文件：** `docs/workorder8-intent-orchestration-tech-spec.md`、
`docs/workorder8-three-party-alignment.md`。

- [ ] 定义 Node A 分流边界：强信号关键词表（复用 `_mock_fraud_score` 的
  `恶意/黑产/套现/刷单/批量/薅羊毛/退款不掉货`，可扩展）命中 → `strong_signal` 跳过 LLM；
  未命中 → `llm_judge` 放行给 Node B。明确 Node A 不改最终确定性路由。
- [ ] 定义 Fallback 语义：`llm_output_parse_fallback`（损坏 JSON）与
  `llm_call_failed`（网络/供应商异常）两个原因码；两者均保守兜底
  （fraud=100 / sentiment=HIGH）并强制人工，禁止静默。
- [ ] 定义评测断言基准：意图召回率 ≥90%、幻觉率 ≤2%、自动化覆盖率 100%、
  混合流 Token 相对纯 LLM 降低 ≥40%；说明每个指标的统计口径与 mock 模式降级规则
  （judge 不可用时按“输出与标注冲突”确定性代理并标注 SKIPPED，不允许跳过样本）。
- [ ] 记录 AI-A/AI-B/人工三方对齐：Node A 过滤边界、Fallback 路由、A/B 基准口径。

验证：文档齐全，规格可被任务二/三直接引用。

## 3. 任务二：双层意图流 + 自动化测试框架（1 人日，Loop Engineering）

### 3.1 先写失败测试

**文件：** `backend/tests/test_intent_filter.py`、`backend/tests/test_eval_pipeline.py`。

- `test_strong_signal_bypasses_llm`：含“刷单”文本 → `route == "strong_signal"`、
  `deterministic_fraud == 88`，且不调用 LLM（mock 客户端断言 0 次调用）。
- `test_normal_complaint_routes_to_llm`：普通客诉 → `route == "llm_judge"`。
- `test_legitimate_refund_not_misclassified`：合法退款材料不命中强信号。
- `test_strong_signal_decision_still_deterministic`：强信号直连 decision 后
  仍为 `HUMAN_REVIEW`（fraud=88 ≥ 阈值，路由语义不变）。
- `test_json_parse_fallback_records_reason`：fake LLM 返回损坏 JSON →
  `fallback_reasons` 含 `llm_output_parse_fallback`，fraud 兜底 100。
- `test_retry_backoff_retries_then_falls_back`：fake 连续抛 3 次异常 →
  `retry_call` 调用底层 3 次后返回保守值，`fallback_reasons` 含 `llm_call_failed`。
- `test_eval_runner_metric`：runner 输出含 `intent_recall` / `hallucination_rate` /
  `coverage` / `avg_ttft_ms` / `total_tokens`；30 条样本覆盖率 100%。
- `test_worker_dlq_on_final_failure`：`process` 抛异常 → 死信流
  `stream:tickets:dead` 新增记录（含 ticket_id、trace_id、error_code）。
- `test_eval_pipeline_30_colloquial_samples`：30 条内联口语样本（情绪化/口语化表述
  映射本项目客诉/退款场景），断言 IntentFilter 分流与标注一致。

### 3.2 实现意图过滤与双层流

**文件：** `backend/app/agents/intent.py`、`backend/app/agents/state.py`、
`backend/app/agents/nodes.py`、`backend/app/agents/graph.py`。

`intent.py` 核心接口（后续任务引用此签名）：

```python
@dataclass(frozen=True)
class IntentResult:
    route: Literal["strong_signal", "llm_judge"]
    label: str                          # refund_request / complaint / malicious / general
    hit_rules: list[str]
    deterministic_fraud: int | None = None
    deterministic_sentiment: RiskLevel | None = None

class IntentFilter:
    def classify(self, text: str) -> IntentResult: ...
```

- [ ] `state.py` 新增字段：`intent_route: str`、`intent_label: str`、
  `intent_hit_rules: list[str]`、`fallback_reasons: list[str]`。
- [ ] `intent_node`：对 `masked_ocr_text or ocr_text` 调 `IntentFilter.classify`，
  写入上述字段；命中强信号时同时写入确定性 `fraud_score`/`sentiment`（供直连 decision）。
- [ ] `graph.py`：`critic → intent`；条件边 `route_intent`：
  `strong_signal → decision`，`llm_judge → risk`；`risk → fallback(条件) → decision`，
  其中 fallback 仅在 `fallback_reasons` 非空时写入 `decision_reasons`。
- [ ] `fallback_node`：把 `fallback_reasons` 合并进 `decision_reasons`
  （如 `llm_output_parse_fallback`），确保审计可见；不改变保守值语义。

### 3.3 重试、DLQ 与展示接入

**文件：** `backend/app/config.py`、`backend/app/agents/llm.py`、
`backend/app/worker/consumer.py`、`frontend/src/components/FlowCanvas.tsx`、
`frontend/src/pages/TicketDetail.tsx`。

- [ ] `config.py`：`LLM_RETRY_MAX_ATTEMPTS=3`、`LLM_RETRY_BASE_DELAY_SECONDS=1.0`、
  `DLQ_STREAM_KEY="stream:tickets:dead"`、`INTENT_FILTER_ENABLED=true`。
- [ ] `llm.py`：`retry_call(fn, *, attempts, base_delay, sleep_fn=time.sleep)` 指数退避
  （退避 1s/2s，sleep 可注入便于测试）；`score_fraud_with_usage_and_reason` /
  `classify_sentiment_with_usage_and_reason` 返回 `(值, usage, reason | None)`；
  `score_risk_parallel_with_usage_and_fallbacks` 追加返回 `fallback_reasons: list[str]`。
- [ ] `consumer.py`：`_NODE_DISPLAY` 增加 `"intent": "Intent"`、`"fallback": "Fallback"`；
  `run_once` 异常分支先 `XADD` 到 `DLQ_STREAM_KEY`（ticket_id/thread_id/trace_id/
  error_code/error_message/retry_count=0/时间戳），再 `mark_failed` + XACK。
- [ ] 前端：FlowCanvas 节点列表增加“意图识别”“异常兜底”；TicketDetail 展示
  意图分流结果与兜底原因（复用现有安全校验标签区域风格）。

验证：

- `pytest backend/tests/test_intent_filter.py backend/tests/test_eval_pipeline.py -q` 全过；
- `pytest backend/tests/test_graph.py backend/tests/test_decision_rules.py backend/tests/test_worker_evaluation.py -q` 无回归；
- `npm run build` 通过（涉及前端改动后）。

## 4. 任务三：A/B Benchmark 与周期报告（1 人日）

**文件：** `evals/intent/intent_samples.jsonl`、`backend/app/evaluation/runner.py`、
`scripts/run_ab_benchmark.py`、`scripts/schedule_periodic_eval.py`。

- [ ] 构造 `intent_samples.jsonl` ≥100 条，字段：
  `case_id / text / expected_label / expected_route / supporting_text`；
  覆盖退款申请、投诉、恶意刷单、口语化/情绪化表述、长文本截断等类别；
  全部映射本项目客诉/退款场景，不引入真实医疗业务。
- [ ] `runner.py`：`run_periodic_eval() -> dict` 一键执行 Golden + 安全网关 +
  意图样本；输出 `docs/evidence/periodic-eval-report.md`，指标含
  `intent_recall`（≥0.90）、`hallucination_rate`（≤0.02）、`coverage`（=1.0）、
  `avg_ttft_ms`、`total_tokens`、异常数与错误码分布（复用 Worker 轨迹 + Langfuse trace）。
- [ ] `run_ab_benchmark.py`：对 100 条样本分别跑纯 LLM 路由与双层混合流，
  记录 Token/TTFT/意图准确率，输出 `docs/evidence/ab-benchmark-report.md`
  对比表与 Token 降低率（目标 ≥40%）。
- [ ] `schedule_periodic_eval.py`：`--time`（默认 02:00）创建 Windows 计划任务
  （`schtasks /Create`，固定可执行文件 + 参数数组）或打印容器内 cron 行；
  `--run-now` 立即执行 runner。

验证：

- `pytest backend/tests/test_eval_pipeline.py -q` 全过；
- `python scripts/run_ab_benchmark.py` 出报告且 Token 降低率 ≥40%；
- `python -m app.evaluation.runner`（或等价入口）出周期报告且覆盖率 100%。

## 5. 任务四：兜底审计与面试 QA（0.5 人日）

**文件：** `docs/evidence/fallback-audit-report.md`、`docs/interview-qa-workorder8.md`。

- [ ] 审计覆盖 4 类异常：LLM 网络故障（重试 2 次后兜底）、拒绝响应（空/异常响应）、
  损坏 JSON（`llm_output_parse_fallback`）、路由死循环（graph 条件边可达性检查）；
  确认 DLQ 记录含 trace_id/error_code，可用 `redis-cli XRANGE stream:tickets:dead - +` 复核。
- [ ] 输出《AI 代码输出异常兜底机制审计报告》，含测试证据与结论。
- [ ] 按工单 8 两个面试题编写答辩话术：多 Agent 协同编排与双层意图识别的落地；
  周期性自动化测试与 Token 成本控制（A/B 实测数据 + 报告路径）。

验证：审计报告覆盖指定检查项；QA 库覆盖 2 个面试题且引用真实代码与报告。

## 6. 最终回归与收尾

- [ ] `pytest backend/tests -q` 全过；`scripts/evaluate_golden.py` 10/10；
  `npm run build` 通过；`git diff --check` 无空白错误。
- [ ] `run_ab_benchmark.py` 与周期 runner 各出一份报告；`git status` 核对无临时文件残留。
- [ ] 确认未修改鉴权/迁移/密钥；沙箱相关保持推迟；DLQ 样本可审计（清理压测数据）。

## 7. 风险与决策门禁

| 风险 | 门禁 | 处理 |
| --- | --- | --- |
| Node A 规则误分流 | 30 条口语样本 + 合法输入回归 | 误分流率记录，命中只影响是否调 LLM，不改最终路由 |
| LLM 幻觉/损坏 JSON | Fallback 显式原因 + 保守兜底 | `llm_output_parse_fallback` 审计可见，绝不静默 |
| 重试放大故障 | 重试上限 2 次 + 指数退避 | 仍失败进 DLQ，不阻塞主流程 |
| 评测脚本影响业务 | runner 只读样本与观测副本 | 不改路由，报告独立归档 |
| 沙箱不可用 | 本计划不依赖沙箱 | 维持推迟 |

## 8. 执行顺序

`任务一规格` → `任务二实现（先测试后代码，Loop）` → `任务三 A/B 与周期报告` →
`任务四审计 QA` → `最终回归`。
