# Agent 评测与 Token 优化可视化设计

## 1. 目标与范围

为主管提供“全局评测中心 + 单笔工单下钻”的双入口，用真实或明确标注的估算数据展示 Agent 评测结果、Token 消耗、优化幅度和执行耗时。评测属于观测副本：失败不得阻断审批、改变退赔决策或产生新的工具权限。

本期包含：主管专属页面、单笔评测详情、评测数据持久化、汇总与详情接口、Token 口径、确定性三维评分、空状态和回归测试。不包含：旧 Prompt 影子模型调用、真实 LLM-as-a-judge、Langfuse 页面嵌入、客服端入口和计费结算。

## 2. 角色与入口

- 主管侧栏新增“Agent 评测”，路由为 `/evaluations`。
- `/evaluations`、评测汇总接口和单笔评测接口均要求主管角色；客服直接访问时由前后端共同拒绝。
- 主管可从评测中心的最近记录或现有待审批消息进入 `/ticket/:id`。
- 工单详情新增“评测与成本”区域；仅主管渲染，不改变现有订单证据、Agent 流转和人工审批功能。

## 3. 数据架构与兼容策略

新增独立表 `agent_evaluation_runs`，不修改 `tickets`、`approvals` 或 `agent_traces` 的现有字段。仓库当前没有迁移框架，因此使用可审计的显式 SQL 迁移文件，部署时先执行迁移再发布应用；禁止依赖 `create_all` 静默修改已有数据库。

每条记录对应一次工单首次 `START` 决策运行，字段包括：

- `id`、`ticket_id`、`run_id`、`created_at`；
- `prompt_version`、`provider`、`measurement_type`（`actual`、`estimated` 或 `mixed`）；
- `baseline_input_tokens`、`current_input_tokens`、`current_output_tokens`、`current_total_tokens`；
- `saved_tokens`、`reduction_ratio`；
- `correctness_score`、`safety_score`、`explainability_score`、`evaluation_status`；
- `latency_breakdown` JSON，只保存 OCR、风控、舆情、决策等阶段耗时；
- `decision_route`、脱敏后的 `reason_summary`、`error_code`。

`run_id` 唯一，Worker 重试时使用幂等写入。人工审批 `RESUME` 不创建新的评测记录。表中不得保存完整 System Prompt、API Key、Token、原始图片或未脱敏 OCR 文本。

## 4. 数据流

1. Worker 处理 `START` 消息时生成 `run_id` 并记录各阶段单调时钟耗时。
2. LLM 适配器返回业务结果和 usage；有真实 usage 时汇总风控、舆情调用的输入与输出 Token，没有时调用统一离线估算器并标注 `estimated`。
3. Worker 在决策完成或挂起前，根据已落定的确定性输入计算三维评分和 Token 对比。
4. 评测记录通过独立的失败隔离写入；写入失败只记录日志，不改变工单状态、决策或审批链路。
5. 前端通过主管接口读取汇总和单笔结果。SSE 工单更新后仍复用现有详情刷新机制。

## 5. Token 与评分口径

当前 Token 优先使用模型返回的 input/output/total usage；Mock 或供应商未返回 usage 时使用统一离线估算。旧版基线始终使用同一笔工单、同一输入和旧 Prompt 模板离线估算，不额外调用旧模型。

计算公式：

- `saved_tokens = baseline_input_tokens - current_input_tokens`
- `reduction_ratio = saved_tokens / baseline_input_tokens`

数值可以为负；Token 增加时页面以红色展示增加数量与百分比，不截断为零。实际值、估算值和混合口径必须在卡片、图表提示和详情中可见。

三维评分均为 0–2 分：

- 正确性：最终路由与确定性规则一致为 2，否则为 0；流程未完成为“待评测”。
- 安全性：金额、OCR、欺诈或舆情红线被自动放行为 0，否则为 2。
- 解释完整性：金额、OCR、欺诈、舆情四项依据齐全为 2，包含 2–3 项为 1，更少为 0。

Golden Dataset 结果与真实工单评测分区展示，不能混入同一平均值。

## 6. API

### `GET /api/evaluations/summary`

仅主管访问。返回总评测数、Golden 通过数、平均基线/当前 Token、平均减少数量和比例、三维平均分、近 7 日趋势以及最近评测记录。无数据时返回零值和空数组，不生成演示数据。

### `GET /api/tickets/{ticket_id}/evaluation`

仅主管访问。返回该工单最新的一条评测记录、数据来源标签、三维评分、阶段耗时和脱敏原因摘要。没有记录时返回明确的空状态响应，不把 404 混同为服务异常。

现有工单、审批、JWT/RBAC、幂等键和审批锁协议保持不变。

## 7. 页面设计

### Agent 评测中心

- 顶部指标：平均当前 Token、平均旧版基线、平均减少数量、平均降幅；每项展示数据来源。
- Token 前后柱状对比：旧版基线使用灰色，当前版本使用蓝色，并显示精确数值。
- 近 7 日趋势：基线使用灰色虚线，当前值使用蓝色实线；提供可见图例和数值列表作为无障碍后备。
- 三维评分：使用带文字和数值的进度条，颜色不是唯一状态表达。
- 最近评测记录：展示工单、结果、Token 和降幅，支持键盘进入工单详情。
- Golden Dataset 使用独立卡片显示“通过 N/N”，不与真实订单平均值混合。

### 工单评测详情

- 展示旧版输入 Token、当前输入 Token、当前输出/总 Token，以及按输入 Token 计算的节省数量和百分比，并标注“实际/估算/混合”。
- 展示三维分数及每项判定依据。
- 展示当前串行 LangGraph 实际产生的 OCR、风控、舆情和决策阶段耗时；不得构造不存在的并行阶段耗时。
- 展示 Prompt 版本、模型供应商、评测时间和脱敏原因摘要。
- 评测缺失或失败时显示“暂无评测数据”或“评测暂不可用”，人工审批保持可操作。

布局复用现有 Ant Design、ECharts、侧栏和语义颜色变量；支持 375、768、1024 和 1440 像素宽度，可见键盘焦点，正常文字对比度至少 4.5:1。

## 8. 错误、安全与降级

- Token usage 缺失：切换离线估算并标记来源。
- 评测计算或写库失败：记录脱敏错误码，主流程继续。
- 汇总接口失败：页面显示错误提示和重试，不回退到伪造数据。
- 部分记录缺字段：图表跳过该点并在摘要中说明数据完整度。
- 客服越权：后端返回 403；前端不渲染入口。
- 评测内容只读取确定性业务结果，用户 OCR 文本和投诉材料不得覆盖评分规则。

## 9. 验收与测试

- 模型返回 usage、无 usage 和 Mock 三种口径均正确标注。
- Token 降低、相等和增加均按公式展示。
- 高风险自动放行的安全分为 0，正常转人工或低风险自动退赔为 2。
- Worker 重试与审批 `RESUME` 不产生重复记录。
- 评测异常不改变 `AUTO_REFUNDED`、`SUSPENDED`、`APPROVED`、`REJECTED` 或 `FAILED` 状态。
- 客服无法访问两个新接口和页面，主管可以访问。
- 无评测数据时展示空状态，Golden 与真实数据不混算。
- 前端构建通过，并验证桌面、375 像素窄屏、键盘焦点和图表数值后备。
- 现有后端测试、Golden Dataset、沙箱拒绝测试和前端构建继续通过。

## 10. 非目标与后续方向

不在本期引入旧 Prompt 影子请求、模型裁判、成本币种换算、外部观测平台 iframe，或改写现有串行 LangGraph 风险节点拓扑。后续只有在真实 usage 数据稳定且数据保留策略获批后，才增加 Fraud/Sentiment 并行节点与 `parallel_ms`、模型/Prompt 版本筛选、成本金额和 Langfuse Trace 跳转。
