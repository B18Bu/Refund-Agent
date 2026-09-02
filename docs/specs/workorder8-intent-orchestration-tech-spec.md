# 双层意图识别与自动化测试系统——设计说明书

> 对应工单 8《多Agent协同-编排、意图与自动化测试系统（基于 LangGraph 的多级意图识别
> 异常兜底与周期性自动化测试评估）》。实现依据：`docs/workorder8-implementation-plan.md`。
> 日期：2026-08-31

## 1. 目标

在客诉舆情退赔决策系统中显式建立“确定性规则过滤（Node A）+ LLM 判定（Node B）”的双层
意图识别流，解决口语化/情绪化输入导致 LLM 幻觉误分类的问题；为 LLM 输出异常建立显式
Fallback 与死信队列；从零构建可定时触发、可输出指标报告的自动化评测框架，并以 A/B 对比
验证混合流的 Token 成本优势。

## 2. 架构

```
OCR/客诉材料 ──> critic（安全网关，已有）──> intent（Node A 确定性过滤）
                ├─ 命中强信号 → 直接决策（跳过 LLM，fraud=88 / sentiment=HIGH）
                └─ 未命中 → risk（Node B：fraud/sentiment 并行 LLM）
                      └─ 解析/调用失败 → fallback 节点（显式记录原因 + 保守兜底）
──> decision（确定性规则）──> human_review（interrupt 挂起）
```

职责边界：

- Node A 只做“过滤/分流”，不改变 `decision_rules.decide` 的确定性路由语义；
  命中强信号时写入的欺诈分/舆情值仍由 decision 层按原阈值裁决。
- Node B 复用现有 `LlmRiskClient` 的 fraud/sentiment 并行分析；LLM 只做增强判断。
- `fallback` 节点仅在 `fallback_reasons` 非空时进入，保证异常路径显式、可审计。

## 3. 双层意图识别

### 3.1 Node A：确定性意图过滤（`backend/app/agents/intent.py`）

核心接口：

```python
IntentResult:
    route: Literal["strong_signal", "llm_judge"]
    label: Literal["refund_request", "complaint", "malicious", "general"]
    hit_rules: list[str]
    deterministic_fraud: int | None
    deterministic_sentiment: RiskLevel | None

IntentFilter.classify(text: str) -> IntentResult
```

分流规则：

- 命中强信号关键词（恶意/黑产/套现/刷单/批量/薅羊毛/退款不掉货/洗钱/伪造凭证/
  PS 凭证/假图/虚构订单）→ `route="strong_signal"`、`label="malicious"`、
  `deterministic_fraud=88`、`deterministic_sentiment="HIGH"`。
- 未命中 → `route="llm_judge"`；`label` 由轻量规则给出提示值：
  含退款/退货/退钱/赔偿/赔付 → `refund_request`；
  含投诉/曝光/维权/愤怒/黑猫 → `complaint`；其余 → `general`。

分流只影响“是否调用 LLM”，不影响最终路由：强信号路径的欺诈分 88 ≥ 阈值 50，
decision 层必然 HUMAN_REVIEW（宁挂勿错退）。

### 3.2 Node B：LLM 判定（复用 `risk_node` 并行分析）

- 输入材料使用 `masked_ocr_text`（DLP 脱敏后），PII 不以明文进入模型。
- 并行执行 fraud/sentiment，单项异常不取消另一项
  （`asyncio.gather(..., return_exceptions=True)`）。
- LLM 输出到意图标签的映射为确定性规则（非模型判断）：
  fraud ≥ 50 → `malicious`；sentiment=HIGH → `complaint`；
  材料含退款语义 → `refund_request`；其余 → `general`。

### 3.3 状态字段（`backend/app/agents/state.py`）

```python
intent_route: str          # strong_signal | llm_judge
intent_label: str          # 展示/审计用
intent_hit_rules: list[str]
fallback_reasons: list[str]  # llm_call_failed | llm_output_parse_fallback
```

## 4. 异常兜底与死信队列

### 4.1 原因码

- `llm_call_failed`：LLM 网络/供应商异常，重试仍失败后保守兜底。
- `llm_output_parse_fallback`：LLM 响应为损坏 JSON / 非法枚举，解析失败后保守兜底。

两个原因码都必须写入 `fallback_reasons` 并最终合并进 `decision_reasons`；
兜底值恒为 fraud=100 / sentiment=HIGH，强制 HUMAN_REVIEW，禁止静默。

### 4.2 指数退避重试

```python
retry_call(fn, *, attempts=3, base_delay=1.0, sleep_fn=time.sleep)
```

- 首次调用 + 最多 2 次重试，退避 1s/2s；`sleep_fn` 可注入用于测试。
- 配置：`LLM_RETRY_MAX_ATTEMPTS=3`、`LLM_RETRY_BASE_DELAY_SECONDS=1.0`。

### 4.3 死信队列

- 配置：`DLQ_STREAM_KEY="stream:tickets:dead"`。
- Worker 不可恢复异常：`XADD` 到死信流（ticket_id/thread_id/trace_id/error_code/
  error_message/retry_count/ts），再执行原 `mark_failed`（COMPLETED+FAILED）+ XACK。
- DLQ 与原落库并存，供审计复核（`redis-cli XRANGE stream:tickets:dead - +`）。

## 5. 自动化评测体系

### 5.1 样本集（`evals/intent/intent_samples.jsonl`，≥100 条）

```json
{"case_id":"I001","text":"...","expected_label":"refund_request","expected_route":"llm_judge","supporting_text":"..."}
```

- 类别：refund_request / complaint / malicious / general；
  口语化、情绪化、长文本、黑产关键词变体均有覆盖。
- 样本全部映射本项目客诉/退款场景，不引入真实医疗业务。

### 5.2 评测 runner（`backend/app/evaluation/runner.py`）

`run_periodic_eval() -> dict` 一键执行：

- Golden 10 条确定性路由评测；
- 安全网关样本（`evals/security/injection_payloads.jsonl`）拦截率；
- 意图样本双层流评测（强信号直判；LLM 路径按 3.2 映射标签）。

输出指标与口径：

| 指标 | 口径 | 基准 |
| --- | --- | --- |
| intent_recall | 主意图（refund_request）TP/(TP+FN) | ≥90% |
| hallucination_rate | LLM 判定与标注冲突且材料无依据；deepseek 用 LLM-as-a-judge，mock 用确定性代理并标注 SKIPPED | ≤2% |
| coverage | 已执行样本 / 总样本 | 100% |
| avg_ttft_ms | 各 LLM 调用首包耗时均值（非流式近似为单次调用耗时） | 记录 |
| total_tokens | 全部样本的 LLM token 消耗合计 | 记录 |

报告归档：`docs/evidence/periodic-eval-report.md`（按日期追加）。

### 5.3 A/B 成本对比（`scripts/run_ab_benchmark.py`）

- 纯 LLM：100 条样本全部执行 fraud+sentiment LLM 调用。
- 双层混合流：先 IntentFilter，强信号跳过 LLM，其余执行 LLM。
- 指标：Token 消耗、TTFT、意图准确率；Token 降低率 = (纯 LLM − 混合)/纯 LLM。
- 基准：Token 降低率 ≥40%（强信号样本占比约 50%，跳过部分直接省去两组 LLM 调用）。
- 报告：`docs/evidence/ab-benchmark-report.md`，注明 provider 与 measurement_type。

### 5.4 周期调度（`scripts/schedule_periodic_eval.py`）

- `--run-now`：立即执行 runner。
- `--install windows --time 02:00`：创建 Windows 计划任务（每日 02:00，
  固定可执行文件 + 参数数组，不使用 shell=True）。
- `--install cron`：打印容器内 cron 行（`0 2 * * * ...`）供部署方安装。

## 6. 边界与暂不实现

- 不做真实医疗问诊业务；样本映射为本项目客诉/退款场景。
- 不引入重型意图模型；Node A 用关键词树（确定性），Node B 用现有 LLM 客户端。
- 沙箱维持推迟；本方案不依赖沙箱，不执行任意用户代码。
