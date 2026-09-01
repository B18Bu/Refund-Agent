# 智能体编排与周期性测试面试 QA 知识库——工单 8

> 覆盖工单 8 两个面试题，结合本项目真实代码与实测数据作答。
> 日期：2026-08-31

## 面试题 1：多 Agent 协同编排与意图识别如何落地？出现口语化/情绪化输入导致的
模型误分类如何治理？

**答题主线：确定性优先 + 双层分流 + 显式兜底。**

1. **编排**：基于 LangGraph 的 `StateGraph` 串联
   `intake → ocr → critic → intent → risk → decision → human_review`
   （`backend/app/agents/graph.py`），人工审批用原生 `interrupt()` 挂起，
   Worker 消费 Redis Streams 消息并驱动执行。
2. **双层意图识别**：Node A（`backend/app/agents/intent.py`）用确定性关键词树
   过滤强信号（恶意/黑产/套现/刷单/批量/薅羊毛/退款不掉货等），命中即跳过 LLM、
   直接写入确定性欺诈分（fraud=88）→ decision 层仍按原阈值强制人工；
   未命中才放行 Node B（`risk_node` 并行 fraud/sentiment 分析）。
3. **防误分类**：Node A 不参与最终路由裁决（AGENTS.md 规则 5），LLM 只是增强判断；
   强信号样本即使纯 LLM 漏判（mock 下 7/100 失配），双层流仍 100% 正确拦截。
4. **显式兜底**：LLM 返回损坏 JSON / 调用失败时记录
   `llm_output_parse_fallback` / `llm_call_failed` 到 `fallback_reasons` 并合并进
   `decision_reasons`，保守兜底转人工，绝不静默（端到端证据见
   `docs/evidence/fallback-audit-report.md`）。

## 面试题 2：如何从零构建周期性自动化测试并控制 LLM 成本？

**答题主线：样本集 + 一键 runner + A/B 实测 + 定时调度。**

1. **样本集**：`evals/intent/intent_samples.jsonl` 100 条口语化客诉/退款样本
   （退款申请/投诉/恶意/一般咨询，标注期望意图与期望分流），schema 校验拒绝脏数据。
2. **一键评测**：`backend/app/evaluation/runner.py` 聚合 Golden（10 条）、
   安全网关样本（100 条）与意图样本，输出覆盖率 100%、召回率、幻觉率、TTFT、Token；
   报告按日期归档到 `docs/evidence/periodic-eval-report.md`。
3. **A/B 成本**：`scripts/run_ab_benchmark.py` 对 100 条样本分别跑纯 LLM 与双层流，
   实测 Token 降低 49.92%（目标 ≥40%）、意图准确率 93%→100%、TTFT 减半
   （`docs/evidence/ab-benchmark-report.md`）。
4. **周期调度**：`scripts/schedule_periodic_eval.py` 支持
   `--run-now` / Windows 计划任务 / 容器 cron（默认每日 02:00），
   固定可执行文件 + 参数数组，不使用 `shell=True`。
5. **成本控制本质**：强信号样本跳过两组 LLM 调用（省 fraud+sentiment 的 prompt 与输出），
   规则层承担确定性过滤，模型只处理弱信号，是“算力花在刀刃上”的工程取舍。

## 关键代码引用

- 双层流：`backend/app/agents/intent.py`、`backend/app/agents/nodes.py`
- 兜底：`backend/app/agents/llm.py`（`retry_call` / `_and_reason`）
- DLQ：`backend/app/worker/consumer.py`（`stream:tickets:dead`）
- 评测：`backend/app/evaluation/runner.py`、`scripts/run_ab_benchmark.py`
