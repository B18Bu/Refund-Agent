# AI 代码审查报告（工单 5 增量）

> 审查日期：2026-08-31
> 审查范围：Langfuse 链路追踪接入、风险分析并行化、LLM-as-a-judge、压测与容灾演练相关代码
> 审查方式：基于真实代码、diff 与运行日志，禁止以口头解释代替证据。

## 结论

未发现 P0（阻断合并）问题。发现 1 个 P1（环境配置）与 2 个 P2（优化建议），详见下。

## 审查项

### 1. Telemetry 是否阻塞 API/Worker 主流程（P0 红线）

**结论：不阻塞。**

- [queue.py](backend/app/observability/queue.py) 使用有界 `queue.Queue(maxsize=1000)` + 独立 daemon 发送线程；`emit()` 采用 `put_nowait`，队列满时只计数丢弃。
- [langfuse.py](backend/app/observability/langfuse.py) 仅将脱敏 payload 入队后立即返回；HTTP 上报发生在后台线程，`httpx` 超时 5s。
- 实测：Langfuse 密钥无效（401）时，Worker 主流程仍持续处理工单（压测期间最近 2 分钟处理 785 张工单），上报失败仅产生 WARNING 日志，未改变任何审批结果。

### 2. 异步并行是否使用 return_exceptions=True（P0 红线）

**结论：通过。**

- [llm.py](backend/app/agents/llm.py) `score_risk_parallel_with_usage` 使用
  `asyncio.gather(..., return_exceptions=True)`；单项异常分别保守兜底
  （fraud=100 / sentiment=HIGH），不取消另一项，也不自动放行。
- 单测覆盖成功与失败两种路径（`test_parallel_risk_with_usage_*`）。
- 图级验证：`test_graph.py` 全部通过，自动退赔路径仍由确定性规则控制。

### 3. 自动审批是否仍由确定性规则控制（P0 红线）

**结论：通过。** `decision_rules.decide` 仍是唯一路由来源；Langfuse 上报与
LLM-as-a-judge 只读观测，不参与路由、重试或数值转换。

### 4. 敏感数据是否脱敏（P0 红线）

**结论：通过。** `sanitize_payload` 剔除 `api_key/authorization/password/token/secret/ocr_text/raw_text/image`；
Langfuse span 只上传摘要与状态；单测 `test_langfuse_emit_queues_sanitized_trace` 验证原始 OCR 文本不会出现在 span 中。

### 5. trace_id 传播

**结论：已实现。** Worker 在 START 时生成/复用 `trace_id`，写入图状态并持久化到
`tickets.trace_id`（迁移 `20260831_add_tickets_trace_id.sql`，幂等 ADD COLUMN）；RESUME 从 checkpoint 复用。
Langfuse 上报与 API 详情展示同一 trace_id。

### 6. 沙箱 try/finally 与生命周期（推迟项）

**结论：范围调整。** 沙箱整体推迟（见方案文档 1.1）；现有 `policy.py` 路径校验与
`CubeSandboxAdapter.destroy()` 保留，未配置沙箱时显式失败，不静默执行宿主机代码。

## 发现的问题

| 级别 | 问题 | 建议 |
| --- | --- | --- |
| P1（已解决） | Langfuse 初始密钥对 cloud.langfuse.com 返回 401 | 已核对为 `us.cloud.langfuse.com`（美国区），ingestion 上报验证通过（工单 9512 含 4 个 span） |
| P2 | Langfuse 上报失败时逐条打 WARNING，高频失败会刷日志 | 可增加失败计数/节流，聚合告警 |
| P2 | 100 用户压测 P95 约 410ms，高于 300ms 目标 | 增加 API worker 数或连接池、对列表接口分页，见 deploy-report |

## 回归证据

- `pytest backend/tests`：90+ passed（含新增 Langfuse/并行/judge 用例）
- `scripts/evaluate_golden.py`：10/10
- `scripts/measure_prompt_tokens.py`：reduction 64.4%（≥30%）
- 前端 `npm run build`：通过
