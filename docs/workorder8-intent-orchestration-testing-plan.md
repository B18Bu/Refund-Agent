# 编排、意图与自动化测试系统——当前项目优化方案

> 文档定位：针对工单 8《多Agent协同-编排、意图与自动化测试系统（基于 LangGraph 的
> 多级意图识别异常兜底与周期性自动化测试评估）》，结合本仓库（客诉舆情退赔决策系统）
> 现有架构制定可落地的优化方案。日期：2026-08-31

## 1. 工单 8 核心要求

1. **多级意图识别**：用 LangGraph 编排“静态规则/轻量模型过滤（Node A）+ LLM（Node B）”
   双层意图识别，解决口语化/情绪化输入导致 LLM 幻觉误分类的问题。
2. **异常兜底**：LLM 返回损坏 JSON / 网络抖动 / Token 溢出时，必须有 Output Parse Fallback，
   禁止下游崩溃；网络故障强制指数退避重试 + 死信队列（DLQ）。
3. **周期性自动化测试**：从零构建自动化测试框架，支持一键定时触发、自动抓取执行日志、
   输出指标报告（TTFT、Token 消耗、意图召回率、幻觉率）。
4. **A/B 成本对比**：纯 LLM 路由 vs 双层混合流，Token 消耗降低 ≥40%。

验收红线：自动化运行覆盖率 100%；意图召回率 ≥90%；幻觉率 ≤2%；混合流 Token 消耗
相对纯 LLM 降低 40%；测试样本集 ≥100。

## 2. 当前项目现状盘点

### 2.1 已具备的能力（可复用，不重复建设）

| 能力 | 位置 | 与工单 8 的关系 |
| --- | --- | --- |
| LangGraph 决策流 + interrupt 挂起 | `agents/graph.py`、`nodes.py` | 双层节点可直接编排 |
| 确定性规则层 | `decision_rules.py` | 天然是“Node A 静态规则” |
| LLM 层（欺诈/舆情） | `agents/llm.py` | 天然是“Node B LLM” |
| LLM 输出解析兜底 | `llm.py`（json 解析失败 → 100/HIGH 保守值） | Output Parse Fallback 雏形 |
| 评测体系 | Golden 10 条 + 确定性评分 + LLM-as-a-judge | 可扩展为周期性 runner |
| Token 基线 | `scripts/measure_prompt_tokens.py`（64.4%） | A/B 对比基础 |
| 可观测 | Langfuse trace + TraceContext + TelemetryQueue | 周期报告数据源 |
| 异常落库 | Worker `mark_failed`（COMPLETED+FAILED+error_code） | 死信审计基础 |

### 2.2 缺口（工单 8 要求、本项目没有）

| 缺口 | 现状 |
| --- | --- |
| 显式“意图识别”双层节点 | 风险分析是双层雏形，但未显式建模“意图分级/分流拦截边界” |
| 损坏 JSON 的显式 Fallback 节点 | 解析失败只保守兜底，无 `llm_output_parse_fallback` 原因记录与路由 |
| 周期性自动化测试调度 | 只有一次性脚本（evaluate_golden/judge_golden/run_red_blue_test） |
| A/B Benchmark 脚本 | 无“纯 LLM vs 双层”对比脚本与报告 |
| 重试与死信队列 | Worker 单次尝试即 FAILED，无指数退避重试、无 DLQ |
| 复杂口语意图样本集（≥100） | 无 |
| 相关文档 | 无《方案设计说明书》《测试报告》《兜底审计报告》《QA 库》 |

## 3. 目标架构

### 3.1 双层意图识别（映射现有 risk 节点）

```
OCR/客诉材料 ──> Node A：静态规则意图过滤（Trie/正则树）
                  ├─ 命中强信号（黑产/刷单/恶意/急诊式关键词）→ 直接裁决（不调 LLM）
                  └─ 未命中 → Node B：LLM 意图判定（fraud/sentiment 并行）
                        └─ LLM 输出解析失败 → Fallback 节点（保守值 + llm_output_parse_fallback）
──> decision（确定性规则）──> human_review（interrupt）
```

- Node A：复用并扩展 `decision_rules`/`_mock_fraud_score` 的关键词树，新增“意图分流”：
  强信号直接给高分意图；弱信号放行给 LLM。
- Node B：现有 `score_risk_parallel_with_usage`；解析失败显式记录
  `llm_output_parse_fallback` 到 `decision_reasons`，路由保持保守人工。
- 拦截边界：Node A 只做“过滤/分流”，不改变最终确定性路由；LLM 只做增强判断。

### 3.2 周期性自动化测试引擎

- `eval/runner.py`：一键运行全部评测（Golden + 安全网关 + 意图样本），
  计算并输出 `docs/evidence/periodic-eval-report.md`：
  - 意图召回率（目标 ≥90%）、幻觉率（≤2%）、自动化覆盖率（100%）、TTFT、Token 消耗。
- 调度：新增 `scripts/schedule_periodic_eval.py`（Windows 计划任务/容器内 cron 两种方式），
  默认每日 02:00 触发；报告按日期归档。
- 日志抓取：复用 Worker 轨迹 + Langfuse trace，统计异常数与错误码分布。

### 3.3 异常兜底与死信队列

- LLM 调用：指数退避重试（默认最多 2 次，退避 1s/2s），仍失败走保守兜底。
- 死信队列：Worker 处理失败的消息 XADD 到 `stream:tickets:dead`
  （含原因、trace_id、重试次数），与原 `mark_failed` 并存用于审计。
- 损坏 JSON：显式 Fallback 节点记录原因，禁止静默兜底。

## 4. 实施任务拆解（对应工单 8 阶段任务）

### 任务一：方案设计与三方对齐（0.5 人日）

产出：
- 《双层意图识别与自动化测试方案设计说明书》：Node A/B 分流边界、Fallback 语义、
  测试前置路径设计、断言基准（召回率 ≥90%、幻觉率 ≤2%）。
- 《三方需求互评与测试策略记录》。

### 任务二：双层意图流 + 自动化测试框架（1 人日，Loop Engineering）

产出：
- `tests/test_eval_pipeline.py`：30 个复杂口语意图样本（含医疗式强情绪表述映射到本项目客诉）。
- `agents/intent.py`：Node A 静态意图过滤（Trie/正则树）与分流。
- `agents/nodes.py`：risk 节点升级为双层 + Fallback 节点（显式 `llm_output_parse_fallback`）。
- `eval/runner.py`：一键执行并输出 Recall/TTFT/Token/幻觉率。
- 测试：`test_json_parse_fallback`、`test_eval_runner_metric`。

验收：30 个样本全跑通；测试框架支持一键定时触发并抓取执行日志。

### 任务三：A/B Benchmark 与周期报告（1 人日）

产出：
- `evals/intent/intent_samples.jsonl`：≥100 条复杂意图样本（标注预期意图/期望路由）。
- `scripts/run_ab_benchmark.py`：纯 LLM 路由 vs 双层混合流各跑 100 条，
  记录 Token/TTFT/准确率，生成 Markdown 对比表。
- `docs/evidence/ab-benchmark-report.md` + 周期性评测报告。

验收：混合流 Token 消耗相对纯 LLM 降低 ≥40%；覆盖率 100%。

### 任务四：兜底审计与面试 QA（0.5 人日）

产出：
- 《AI 代码输出异常兜底机制审计报告》：覆盖 LLM 网络故障/拒绝响应/损坏 JSON/路由死循环，
  确认重试与 DLQ 生效。
- 《智能体编排与周期性测试面试 QA 知识库》：覆盖工单 8 两个面试题。

## 5. 验收标准映射

| 工单 8 产出物 | 本项目对应交付 | 验收红线 |
| --- | --- | --- |
| 《方案设计说明书》《测试策略记录》 | docs + 三方记录 | 前置路径 + 断言基准明确 |
| LangGraph 意图流 + 测试框架源码 | intent.py + runner.py | 一键定时触发、日志抓取 |
| 样本集 + 周期测试报告 | intent_samples.jsonl + 报告 | 覆盖率 100%、召回率 ≥90%、幻觉率 ≤2% |
| A/B 对比 | run_ab_benchmark.py + 报告 | 混合流 Token 降低 ≥40% |
| 兜底审计 + QA 库 | 审计报告 + QA 库 | 覆盖 2 个面试题 |

## 6. 风险与门禁

| 风险 | 门禁/处理 |
| --- | --- |
| Node A 规则误分流 | 样本回归 + 合法输入用例，误分流率记录 |
| LLM 幻觉/损坏 JSON | Fallback 保守兜底 + `llm_output_parse_fallback` 审计，绝不静默 |
| 重试放大故障 | 退避上限 2 次；仍失败进 DLQ，不影响业务主流程 |
| 评测脚本影响业务 | runner 只读观测副本与样本，不改路由 |
| 沙箱/工单 6 能力 | 复用不冲突，保持既有安全网关 |

## 7. 边界与暂不实现

- 不做真实医疗问诊业务：样本映射为本项目客诉/退款意图场景，验证同一套双层与评测机制。
- 不引入重型意图模型：Node A 用 Trie/正则树（确定性），Node B 用现有 LLM 客户端。
- 沙箱维持推迟；本方案不依赖沙箱。
