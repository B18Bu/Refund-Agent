# 企业级 Agent 零信任安全防护与 AI 治理——当前项目优化方案

> 文档定位：针对工单 6《多Agent协同-企业级Agent零信任安全防护与AI治理系统》，
> 结合本仓库（客诉舆情退赔决策系统）现有架构制定可落地的优化方案。
> 日期：2026-08-31

## 1. 工单 6 核心要求

在 AI 治理层建立主动防御，解决两类风险：

1. **间接提示词注入（Indirect Prompt Injection）**：用户输入中夹带“跳过人工审批、
   调用 Direct_Refund_API 原路退回”等恶意指令，劫持 Actor Agent 绕过审批。
2. **敏感数据泄露（DLP）**：手机号、身份证、交易密码等 PII 被明文喂给 LLM 并打印在日志中。

要求交付：前置 **Critic Agent（语义安全路由器）**（规则/轻量模型双引擎，风险概率≥0.85 拦截）、
**DLP 脱敏模块**（正则 + NER，脱敏准确率≥99%）、**100+ 对抗样本红蓝测试**（注入拦截率≥95%、
越狱防御成功率≥98%）、安全审计与面试 QA。

## 2. 当前项目安全现状盘点

### 2.1 已具备的能力（不重复建设）

| 能力 | 位置 | 说明 |
| --- | --- | --- |
| 认证与 RBAC | `backend/app/security.py`、`deps.py` | JWT + 角色（CS/SV） |
| 上传文件校验 | `storage.py` | MIME + 魔数 + 重命名 + sha256 |
| 审批并发防护 | `locks.py` + DB 条件更新 | 审批锁 + 原子状态机 |
| 幂等 | `idempotency.py` | Redis SET NX |
| 决策确定性规则 | `decision_rules.py` | 用户材料为不可信输入，规则是唯一路由来源 |
| 上报脱敏 | `observability/tracing.py` | Langfuse 只上报脱敏摘要 |
| 沙箱护栏 | AGENTS.md | 未配置沙箱显式失败（沙箱实现推迟） |

### 2.2 缺口（工单 6 要求、本项目没有）

| 缺口 | 现状证据 |
| --- | --- |
| Critic Agent（注入/越狱检测） | 决策流无任何前置语义安全检查节点 |
| 输入侧 DLP（PII 脱敏） | 只有“上报脱敏”，用户投诉文本/OCR 明文进入 LLM 与日志 |
| 危险 Tool 指令过滤 | 无“跳过人工审批/直接退款”类指令识别与阻断 |
| 对抗测试环境 | 无注入样本库、无红蓝脚本、无拦截率报告 |
| 安全规格文档 | 无 `docs/sec_spec.md`、无《技术说明书》《三方对齐记录》 |

## 3. 目标架构（集成进现有 LangGraph 决策流）

```
API 建单 ──> Redis Streams ──> Worker
  intake ──> OCR ──> security（新增：DLP 脱敏 + Critic 注入检测）──> risk ──> decision ──> human_review
```

> 节点顺序说明：Critic 需要 `ocr_text` 才能检测图片内嵌的间接注入，故安全网关置于 OCR 之后。

### 3.1 安全网关模块 `backend/app/security/gateway.py`

- **DLP（敏感数据脱敏）**：
  - 正则白名单：手机号 → `138****0000`；身份证 → `110***********1234`；银行卡；
    API Key/密钥（`sk-`/`pk-lf-` 等）→ `sk-****`；邮箱/座机。
  - NER 增强（可选）：`LLM_PROVIDER=deepseek` 时对未命中正则的实体做二次识别，失败不影响主流程。
  - 输出：掩码后的安全文本，供 LLM/日志/Telemetry 使用；原始文本仅存库供审计（不随 trace 上报）。
- **Critic（语义安全路由器）**：
  - 规则引擎：注入特征正则库（间接注入指令、角色扮演越狱、Base64 变体、多语言注入、系统提示篡改、
    “跳过/绕过/直接调用/退款 API”等），按命中权重输出 0~1 风险分。
  - 可选 LLM 增强：deepseek 可用时二次打分，结果仅增强不改变规则结论。
  - 阈值：风险分 ≥ 0.85 → 拦截（对应工单 6 决策阈值）。
  - 拦截动作：抛 `SecurityException` → 工单强制转人工并记录 `security_injection_detected`，
    绝不进入 AUTO_REFUND；同时写入审计轨迹。

### 3.2 决策流集成

- `graph.py`：新增 `critic` 节点（intake → ocr → critic → risk → decision）。
- `nodes.py`：`critic_node` 对 `state["ocr_text"]` 与客诉材料先 DLP 脱敏、再 Critic 检测；
  命中则把路由强制置为 HUMAN_REVIEW（reason `security_injection_detected`）。
- `decision_rules.py`：新增 `security_injection_detected` 作为最高优先级红线
  （任何命中都不允许自动退赔）。
- `worker/consumer.py`：轨迹与 Telemetry 只写掩码文本；`SecurityException` 审计记录。
- `routers/tickets.py`：详情返回脱敏后的文本与安全原因标签。

### 3.3 与现有能力的关系

- 不修改鉴权、审批锁、幂等、RBAC。
- 沙箱继续推迟；Critic/DLP 属于“输入输出治理层”，与沙箱（运行隔离）互补，不依赖沙箱。
- 本项目无真实支付 Tool-Calling（`AUTO_REFUNDED` 仅为决策记录），但仍按工单语义
  拦截“跳过人工审批/直接退款”类指令，防御未来接入真实退款 API 时的越权风险。

## 4. 实施任务拆解（对应工单 6 阶段任务）

### 任务一：安全规格与三方对齐（0.5 人日）

产出：
- `docs/sec_spec.md`：STRIDE 威胁建模、≥5 种注入攻击特征与判定逻辑、PII 实体与掩码格式、
  Critic 阈值（≥0.85）、拦截与降级规则。
- 《Agent 零信任安全防御技术说明书》《三方对齐与防御决策记录》（记录 AI-A/AI-B/人 裁决）。

### 任务二：防注入与脱敏模块（1 人日，Loop Engineering）

产出：
- `backend/app/security/gateway.py`：`DLP.mask(text)`、`CriticEngine.score(text) -> (risk, matched_rules)`。
- `backend/tests/test_security_gateway.py`：10 个用例（合法输入、手机号/身份证/API Key 明文、
  间接注入、Base64 绕过、角色扮演越狱、多语言注入、危险 Tool 指令、阈值边界）。
- 接入 LangGraph（critic 节点 + 决策红线 + 轨迹/Telemetry 掩码）。

验收：手机号/身份证/API Key 脱敏准确率 ≥99%（以样本集统计）。

### 任务三：红蓝对抗与拦截率压测（1 人日）

产出：
- `evals/security/injection_payloads.jsonl`：100 个变种（Base64、Unicode、角色扮演、
  多语言、系统提示篡改、危险 Tool 指令等；标注类别与期望拦截）。
- `scripts/run_red_blue_test.py`：批量执行 DLP + Critic，统计拦截率/漏报率/误报率，
  输出 Markdown 评测报告 `docs/evidence/security-red-blue-report.md`。

验收：注入防御拦截率 ≥95%，越狱防御成功率 ≥98%，DLP 漏报率/误报率记录在案。

### 任务四：代码安全审计与面试 QA（0.5 人日）

产出：
- 《AI 代码安全与敏感数据泄露审计报告》：检查 eval/exec/os.system/shell 拼接（本项目为 0）、
  日志/轨迹 PII 泄漏点、脱敏覆盖范围。
- 《AI 治理与攻防面试 QA 知识库》：按工单 6 指定的 3 个面试题编写结合本项目代码的答辩话术
  （Critic 拦截机制、DLP 掩码、RLS/审批隔离、治理盲区）。

## 5. 验收标准映射

| 工单 6 产出物 | 本项目对应交付 | 验收红线 |
| --- | --- | --- |
| 《技术说明书》/《三方对齐记录》 | docs/sec_spec.md + 记录文档 | 定义 ≥5 种注入防御手段 |
| Critic 网关 + DLP 源码 | security/gateway.py + LangGraph 集成 | 手机号/身份证/API Key 脱敏 ≥99% |
| 红蓝脚本 + 评测报告 | scripts/run_red_blue_test.py + 报告 | 100+ 样本注入拦截率 ≥95%，越狱 ≥98% |
| 审计报告 + 面试 QA | 审计报告 + QA 知识库 | 覆盖 3 个指定面试题 |

## 6. 风险与门禁

| 风险 | 门禁/处理 |
| --- | --- |
| 规则引擎误报伤正常客诉 | 阈值可配；样本集含合法输入回归用例，误报率记录 |
| DLP 误伤正常文本（如座机/编号） | 掩码白名单 + 上下文规则；误报率纳入报告 |
| LLM Critic 可用性 | 规则引擎始终生效；LLM 仅增强，失败不影响拦截 |
| 拦截语义改变路由 | 命中只允许转人工/失败，绝不自动放行；Golden 回归保持 |
| 沙箱不可用 | 本方案不依赖沙箱；运行隔离部分继续推迟 |

## 7. 边界与暂不实现

- 真实退款 API 的端到端越权演练：本项目无真实支付接口，用对抗样本在决策流层面验证
  “拦截→强制人工”语义。
- 生产级 NER 模型训练：用正则 + 可选 LLM 增强，不引入额外重型模型。
- 沙箱/OfficeCLI：维持工单 5 推迟决策。
