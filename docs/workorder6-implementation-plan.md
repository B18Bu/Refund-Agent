# 企业级 Agent 零信任安全防护与 AI 治理——实施计划

> **面向 AI 代理的工作者：** 按任务顺序实施；每个任务完成后运行对应测试并提交可审查变更。
> 实现阶段使用 `subagent-driven-development` 或 `executing-plans`，不得跳过安全门禁。
> 本计划对应方案文档 `docs/workorder6-zero-trust-security-plan.md` 与工单 6。

## 0. 实施边界与成功标准

- 不修改鉴权协议、现有角色、审批锁、幂等键与数据库迁移策略；不触碰生产密钥。
- 安全网关只做“输入治理层”防御：DLP 脱敏 + Critic 注入检测 + 危险 Tool 指令过滤；
  不改变退赔决策的确定性规则语义，沙箱继续推迟。
- 命中注入/越狱：强制 HUMAN_REVIEW（reason `security_injection_detected`），
  绝不进入 AUTO_REFUND；`AUTO_REFUNDED` 仍仅为决策记录，不调用真实支付。
- 节点顺序采用 `intake → ocr → critic → risk → decision`：Critic 需要 `ocr_text`
  才能检测图片内嵌的间接注入，因此放在 OCR 之后（相对方案文档的图示为实施细化）。
- 成功标准：
  - 10 个安全网关测试全过（含合法输入回归，误报可控）；
  - 100+ 对抗样本：注入拦截率 ≥95%、越狱防御成功率 ≥98%；
  - 手机号/身份证/API Key 脱敏准确率 ≥99%（样本集统计）；
  - 后端全量测试、Golden、前端构建无回归。

## 1. 文件变更总览

**新增**

- `docs/sec_spec.md`：安全网关规格（STRIDE、注入特征、PII 掩码、阈值、拦截语义）。
- `docs/workorder6-security-tech-spec.md`：《Agent 零信任安全防御技术说明书》。
- `docs/workorder6-three-party-alignment.md`：《三方对齐与防御决策记录》。
- `backend/app/security/gateway.py`：DLP 脱敏 + CriticEngine（规则评分 + 可选 LLM 增强）。
- `backend/tests/test_security_gateway.py`：10 个安全网关测试。
- `evals/security/injection_payloads.jsonl`：100 个对抗样本（标注类别/期望拦截）。
- `scripts/run_red_blue_test.py`：红蓝对抗批量评测脚本。
- `docs/evidence/security-red-blue-report.md`：拦截率评测报告。
- `docs/evidence/security-audit-report.md`：《AI 代码安全与敏感数据泄露审计报告》。
- `docs/interview-qa-security.md`：《AI 治理与攻防面试 QA 知识库》。

**修改**

- `backend/app/config.py`：安全网关开关与阈值配置。
- `backend/app/agents/state.py`：`critic_risk`、`security_flags` 字段。
- `backend/app/agents/decision_rules.py`：`security_injection_detected` 最高优先级红线。
- `backend/app/agents/nodes.py`：新增 `critic_node`（DLP 掩码 + Critic 检测）。
- `backend/app/agents/graph.py`：接入 `critic` 节点。
- `backend/app/agents/llm.py`：材料改为掩码文本。
- `backend/app/worker/consumer.py`：轨迹/Telemetry 写掩码文本与安全原因。
- `backend/app/routers/tickets.py`：详情返回安全原因与掩码文本。
- `frontend/src/pages/TicketDetail.tsx`：展示“安全校验”标签。

## 2. 任务一：安全规格与三方对齐（0.5 人日）

**文件：** `docs/sec_spec.md`、`docs/workorder6-security-tech-spec.md`、`docs/workorder6-three-party-alignment.md`。

- [ ] 用 STRIDE 对 Agent 输入/工具调用建模，输出威胁清单（欺骗/篡改/否认/信息泄露/拒绝服务/提权）。
- [ ] 定义 ≥5 种提示词注入攻击特征与判定逻辑：
  间接注入指令、角色扮演越狱、Base64/Unicode 绕过、多语言注入、系统提示篡改、危险 Tool 指令。
- [ ] 定义 PII 实体列表与掩码格式：手机号 `138****0000`、身份证、银行卡、API Key/密钥、邮箱。
- [ ] 定义 Critic 阈值（风险分 ≥0.85 拦截）与降级规则（LLM 不可用时规则引擎仍生效）。
- [ ] 记录 AI-A/AI-B/人工三方对齐与裁决结果。

验证：文档齐全，规格可被任务二直接引用。

## 3. 任务二：防注入与脱敏模块（1 人日，Loop Engineering）

### 3.1 先写失败测试

**文件：** `backend/tests/test_security_gateway.py`，10 个用例：

- `test_legitimate_text_not_masked_or_blocked`：正常客诉不误伤。
- `test_dlp_masks_mobile_phone`：`13812340000` → `138****0000`。
- `test_dlp_masks_id_card`：身份证掩码。
- `test_dlp_masks_api_key`：`sk-...` → `sk-****`。
- `test_critic_blocks_indirect_injection`：含“跳过人工审批/调用退款 API”的输入被拦截并抛 `SecurityException`。
- `test_critic_blocks_jailbreak_roleplay`：角色扮演越狱样本被拦截。
- `test_critic_blocks_base64_obfuscation`：Base64 变体被解码后拦截。
- `test_critic_blocks_multilingual_injection`：多语言注入被拦截。
- `test_critic_threshold_boundary`：风险分阈值 0.85 边界行为。
- `test_masked_text_feeds_llm_material`：集成断言 risk 材料不含明文 PII。

### 3.2 实现安全网关

**文件：** `backend/app/security/gateway.py`：

- `DLP.mask(text) -> (masked_text, masked_pii: list[str])`：正则白名单 + 可选 NER 增强；
  只对可识别实体掩码，返回掩码后文本与脱敏实体清单。
- `CriticEngine.score(text) -> tuple[float, list[str]]`：规则特征库逐条命中加权，输出 0~1 风险分与命中规则；
  `LLM_PROVIDER=deepseek` 时可选 LLM 二次评分（失败仅告警，不影响规则结论）。
- `SecurityException`：拦截信号，携带风险分与命中规则。

### 3.3 接入决策流

- [ ] `config.py`：`SECURITY_GATEWAY_ENABLED=true`、`SECURITY_INJECTION_THRESHOLD=0.85`、
  `DLP_ENABLED=true`、`SECURITY_LLM_ENHANCE=false`。
- [ ] `state.py`：`critic_risk: float`、`security_flags: list[str]`、`masked_ocr_text: str`。
- [ ] `decision_rules.py`：`security_injection_detected` 置于金额/OCR 检查之前，命中即 HUMAN_REVIEW。
- [ ] `nodes.py`：`critic_node` —— 对 `ocr_text` 先 DLP 掩码（存 `masked_ocr_text`），再 Critic 评分；
  风险分 ≥ 阈值 → `SecurityException` → 决策强制人工并记录安全原因。
- [ ] `graph.py`：`intake → ocr → critic → risk → decision`。
- [ ] `llm.py`：`fraud/sentiment` 材料使用 `masked_ocr_text`（无掩码时回退原文本）。
- [ ] `worker/consumer.py`：Decision 轨迹含安全原因；Telemetry span 只传掩码摘要。
- [ ] `routers/tickets.py` + 前端：详情返回并展示 `security_flags`/掩码文本。

验证：

- `pytest backend/tests/test_security_gateway.py -q` 全过；
- `pytest backend/tests/test_graph.py backend/tests/test_decision_rules.py -q` 无回归；
- DLP 准确率：对固定 PII 样本集统计 ≥99%（脚本或测试断言）。

## 4. 任务三：红蓝对抗与拦截率压测（1 人日）

**文件：** `evals/security/injection_payloads.jsonl`、`scripts/run_red_blue_test.py`。

- [ ] 准备 100 个对抗样本：间接注入、角色扮演越狱、Base64/Unicode 变体、多语言注入、
  系统提示篡改、危险 Tool 指令（含 10 个合法样本用于误报统计）。
- [ ] `run_red_blue_test.py`：逐样本执行 `DLP.mask` + `CriticEngine.score`，
  统计注入拦截率、越狱成功率、DLP 漏报率/误报率；输出 Markdown 报告
  `docs/evidence/security-red-blue-report.md`。
- [ ] 报告含：样本数、按类别拦截率、阈值调整建议、失败样本明细。

验证：注入拦截率 ≥95%、越狱防御成功率 ≥98%；未达标时报告实测值与差距，不写“已通过”。

## 5. 任务四：代码安全审计与面试 QA（0.5 人日）

**文件：** `docs/evidence/security-audit-report.md`、`docs/interview-qa-security.md`。

- [ ] 审计：`rg` 检查 `eval(`/`exec(`/`os.system(`/`shell=True`/子进程拼接（本项目应为 0）；
  检查日志/轨迹/Telemetry 是否存在明文 PII 输出点（应全部走掩码）。
- [ ] 输出《AI 代码安全与敏感数据泄露审计报告》，含发现项与修复结论。
- [ ] 按工单 6 三个面试题编写答辩话术，结合 Critic 拦截机制、DLP 掩码、审批隔离/RLS、
  治理盲区等本项目实现作答，沉淀《AI 治理与攻防面试 QA 知识库》。

验证：审计报告覆盖指定检查项；QA 库覆盖 3 个面试题且引用真实代码。

## 6. 最终回归与收尾

- [ ] `pytest backend/tests -q` 全过；`scripts/evaluate_golden.py` 10/10；
  `npm run build` 通过；`python scripts/measure_prompt_tokens.py` 保持 ≥30%。
- [ ] `scripts/run_red_blue_test.py` 出报告；`git diff --check` 无空白错误。
- [ ] 确认未修改鉴权/迁移/密钥；沙箱相关保持推迟。

## 7. 风险与决策门禁

| 风险 | 门禁 | 处理 |
| --- | --- | --- |
| 规则误报伤正常客诉 | 10 个合法样本 + 回归 | 阈值可配，误报率记录，不自动放行任何命中 |
| DLP 误伤正常文本 | 白名单与上下文规则 | 掩码实体清单可审计，误报纳入报告 |
| LLM Critic 不可用 | 规则引擎独立生效 | LLM 仅增强，失败仅告警 |
| 拦截改变路由语义 | Golden G10 保持 | 命中只允许转人工/失败 |
| 沙箱不可用 | 本计划不依赖沙箱 | 维持推迟 |

## 8. 执行顺序

`任务一规格` → `任务二实现（先测试后代码，Loop）` → `任务三红蓝对抗` → `任务四审计QA` → `最终回归`。
