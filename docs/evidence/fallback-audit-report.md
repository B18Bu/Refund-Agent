# AI 代码输出异常兜底机制审计报告——工单 8

> 审计对象：双层意图流（Node A 静态过滤 + Node B LLM）、LLM 输出解析兜底、
> 指数退避重试与死信队列。日期：2026-08-31

## 1. 审计范围与结论

覆盖 4 类异常场景，全部通过自动化测试与端到端证据验证，结论：兜底机制生效且可审计，
不存在静默降级路径。

| 异常场景 | 兜底语义 | 证据 | 结论 |
| --- | --- | --- | --- |
| LLM 网络故障 | 指数退避重试（首次 + 最多 2 次，退避 1s/2s），仍失败保守兜底并记录 `llm_call_failed` | `test_retry_backoff_retries_then_falls_back`（调用 3 次后兜底） | 通过 |
| LLM 拒绝/空响应 | 保守兜底（fraud=100 / sentiment=HIGH）并记录 `llm_call_failed` | `score_fraud_with_usage_and_reason` 异常分支 | 通过 |
| 损坏 JSON | 显式 `llm_output_parse_fallback`，保留真实 usage，保守兜底 | `test_json_parse_fallback_records_reason` | 通过 |
| 路由死循环 | 图结构为有向无环（intent 条件边 / risk 条件边 / fallback 单出边），LangGraph 无自环 | `graph.py` 边定义 + 全量图测试 | 通过 |

## 2. 端到端 Fallback 证据

模拟 LLM 返回损坏 JSON 时完整决策流输出：

```
intent_route= llm_judge
fallback_reasons= ['llm_output_parse_fallback']
decision= HUMAN_REVIEW
decision_reasons= ['fraud_score_at_threshold', 'llm_output_parse_fallback']
final_decision= PENDING
```

验证点：

- `fallback_reasons` 显式记录原因，绝不静默；
- `llm_output_parse_fallback` 已合并进最终 `decision_reasons`（`fallback_node` +
  `decision_node` 双保险）；
- 兜底保守值（fraud=100）强制 HUMAN_REVIEW，工单挂起等待人工审批。

## 3. 死信队列审计

- 配置：`DLQ_STREAM_KEY=stream:tickets:dead`（`backend/app/config.py`）。
- Worker 不可恢复异常：先 `XADD` 死信流（ticket_id / thread_id / trace_id /
  error_code / error_message / retry_count / ts），再 `mark_failed` + XACK。
- 自动化证据：`test_worker_dlq_on_final_failure` 断言死信流包含 `trace-dlq-1` 与
  `ERR_PROCESS_FAILED`。
- 人工复核命令：`redis-cli XRANGE stream:tickets:dead - +`。

## 4. 建议

- 生产环境建议为死信流配置保留期/告警（如 7 天清理 + 监控未消费条数）。
- mock 模式下 `judge_status=PROXY` 属预期降级；deepseek 下应复核 JUDGED 幻觉率。
