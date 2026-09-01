# 安全网关规格说明书（docs/sec_spec.md）

> 只读规约：任务二实现与测试均以此为准。对应工单 6《企业级 Agent 零信任安全防护与 AI 治理系统》。

## 1. 威胁建模（STRIDE）

| 威胁 | 场景（本系统） | 防御 |
| --- | --- | --- |
| Spoofing 欺骗 | 伪造图片/凭证诱导自动退赔 | OCR 置信度 + 金额校验 + 注入检测 |
| Tampering 篡改 | 输入夹带“跳过审批/直接退款”指令 | Critic 语义路由（本规格） |
| Repudiation 否认 | 用户否认提交内容 | 工单轨迹 + 掩码审计留痕 |
| Information Disclosure 泄露 | 手机号/身份证/密钥明文进 LLM 与日志 | DLP 脱敏（本规格） |
| DoS 拒绝服务 | 恶意长文本/批量注入消耗 LLM | 规则引擎优先、LLM 仅增强 |
| Elevation of Privilege 提权 | 注入劫持绕过 RBAC/审批 | 命中注入强制人工，绝不放行 |

## 2. 间接提示词注入特征（≥5 类）

1. **间接注入指令**：`跳过人工审批`、`绕过审批`、`直接调用`、`调用后台`、`原路退回`、
   `全额赔付`、`无需人工`、`立即执行`。
2. **危险 Tool 指令**：`退款API`、`Direct_Refund_API`、`支付接口`、`approve` + bypass、
   `直接执行`、`调用.*退款`。
3. **角色扮演越狱**：`忽略之前`、`忽略所有指令`、`你现在是`、`扮演系统`、`作为系统`、
   `developer mode`、`do anything now`、`DAN`。
4. **系统提示篡改**：`system prompt`、`系统提示`、`system message`、`开发者指令`、`规则覆盖`。
5. **编码绕过**：Base64/Unicode/全角/混合大小写变体；解码或归一化后命中上述特征。
6. **多语言注入**：`ignore previous instructions`、`ignore all previous`、
   `前の指示を無視`、`이전 지시 무시` 等跨语言同义指令。

判定逻辑：归一化（小写、全角转半角、Unicode 归一化）→ 正则特征库逐条命中 → 加权评分。

## 3. Critic 评分与阈值

- 风险分 `risk ∈ [0, 1]`：每条命中规则累加权重，上限 1.0。
- 权重（强规则单条命中即拦截）：
  - 强规则 1.0：危险 Tool（`Direct_Refund_API`/`退款API`/`退款接口`/`调用后台`等）、
    直接指令（`跳过人工审批/绕过审批/无需人工/原路退回/全额赔付`）、
    越狱强词（`忽略之前/忽略所有指令`/`developer mode`/`DAN`/`扮演系统`/`系统 mode`等）、
    系统提示篡改、Base64 解码命中危险词、多语言注入（`ignore previous`/`前の指示`/`이전 지시`等）；
  - 弱规则 0.5：`立即执行/直接放行/自动通过/放行` 等弱词，两条弱规则叠加即达拦截阈值。
- 阈值：`risk >= 0.85` → 拦截（对应工单 6 决策阈值）。
- 命中拦截：抛 `SecurityException` → 决策强制 HUMAN_REVIEW（reason `security_injection_detected`），
  记录命中规则；绝不进入 AUTO_REFUND。
- 降级：LLM 增强不可用时规则引擎独立生效，拦截不受影响。

## 4. DLP 脱敏规则（PII 实体与掩码格式）

| 实体 | 掩码格式 | 示例 |
| --- | --- | --- |
| 手机号 | 前 3 + `****` + 后 4 | `13812340000` → `138****0000` |
| 身份证 | 前 3 + `***********`(11) + 后 4 | `110101199001011234` → `110***********1234` |
| 银行卡 | 前 4 + `**********`(10) + 后 4 | `6222021234567890123` → `6222**********0123` |
| API Key/密钥 | 前缀 + `****` | `sk-abcdef123456` → `sk-****`；`pk-lf-xxx` → `pk-lf-****` |
| 邮箱 | 首字符 + `***` + `@域名` | `alice@example.com` → `a***@example.com` |

规则：正则白名单为主；`DLP.mask(text) -> (masked_text, entities)` 返回掩码文本与实体清单；
掩码文本用于 LLM 材料、日志、轨迹与 Telemetry；原始文本仅存内部库用于审计。

## 5. 集成位置

`intake → OCR → critic（DLP 掩码 + Critic 检测）→ risk → decision → human_review`

- `critic` 对 OCR 原文做注入检测；生成 `masked_ocr_text` 供 LLM 与观测使用。
- `decision_rules.decide_with_reasons` 新增最高优先级红线 `security_injection_detected`。

## 6. 验收指标

- DLP：手机号/身份证/API Key 脱敏准确率 ≥99%。
- 红蓝对抗：100+ 样本注入拦截率 ≥95%，越狱防御成功率 ≥98%。
- 回归：合法输入误报率记录在案；Golden 与全量测试无回归。
