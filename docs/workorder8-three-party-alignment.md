# 三方需求互评与测试策略记录——工单 8

> 角色：AI-A（方案设计）、AI-B（实现与测试）、人工（需求方/业务评审）。
> 目的：对齐双层意图识别、异常兜底与自动化评测的边界与验收口径，记录裁决。
> 日期：2026-08-31

## 1. 需求拆解与三方互评

| 需求 | AI-A 解读 | AI-B 落地评估 | 人工评审 | 结论 |
| --- | --- | --- | --- | --- |
| 多级意图识别（Node A 静态 + Node B LLM） | 确定性规则过滤强信号，LLM 只处理弱信号 | 复用 `decision_rules` 关键词与 `risk_node` 并行分析，无新重型模型 | 接受：过滤不改最终路由，符合“金额/欺诈红线确定性”护栏 | 采纳 |
| 输出异常兜底（损坏 JSON / 网络抖动 / Token 溢出） | 显式原因码 + 保守兜底，禁止静默 | 新增 `fallback` 节点与 `fallback_reasons`；解析失败显式记录 | 接受：兜底必须可审计、可解释 | 采纳 |
| 指数退避重试 + 死信队列 | LLM 调用重试 2 次；Worker 异常进 DLQ | `retry_call` 注入式退避；`stream:tickets:dead` XADD 与 `mark_failed` 并存 | 接受：重试上限防放大故障；DLQ 用于审计 | 采纳 |
| 周期性自动化测试（一键定时、抓日志、出报告） | runner 聚合 Golden/安全/意图三类评测 | 复用 `evaluation` 模块与 Langfuse trace；报告按日期归档 | 接受：覆盖率必须 100%，不得静默跳过样本 | 采纳 |
| A/B 成本对比（Token 降低 ≥40%） | 纯 LLM vs 双层流同集对比 | 强信号样本约 50%，跳过即省两组 LLM 调用；报告中注明口径 | 接受：指标口径写入报告，避免“为达标而构造” | 采纳 |

## 2. 关键裁决

1. **Node A 边界**：只做过滤/分流，写入的确定性欺诈分仍走 decision 原阈值；
   强信号路由必然 HUMAN_REVIEW，不产生 AUTO_REFUND。
2. **Fallback 语义**：`llm_call_failed` / `llm_output_parse_fallback` 两个原因码
   必须进入最终 `decision_reasons`；兜底值恒为保守值，绝不静默降级。
3. **评测口径**：intent_recall 按主意图（refund_request）计算；幻觉率在 deepseek
   下用 LLM-as-a-judge，mock 下用确定性代理并标注 SKIPPED；覆盖率按“已执行/总样本”。
4. **A/B 口径**：同一样本集、同一 provider，报告注明 measurement_type
   （actual/estimated），Token 降低率 = (纯 LLM − 混合)/纯 LLM。
5. **沙箱**：维持推迟；本方案不依赖沙箱，不得回退宿主执行。

## 3. 测试策略

- 任务二：先写失败测试（意图分流、Fallback 原因、重试退避、runner 指标、DLQ），
  确认失败后再实现，每个关键步骤运行对应 pytest。
- 回归：`pytest backend/tests -q`、Golden 10/10、`npm run build`、`git diff --check`。
- 证据：周期评测报告、A/B 报告、兜底审计报告归档于 `docs/evidence/`。

## 4. 遗留与待清理

- 前端 FlowCanvas 增加 Intent/Fallback 节点展示；TicketDetail 展示意图与兜底原因。
- 完成后清理压测/演示工单数据（DLQ 样本保留用于审计）。
