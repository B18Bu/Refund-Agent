# Agent 零信任安全防御技术说明书

> 对应工单 6 任务一产出物，规格以 `docs/sec_spec.md` 为准。

## 1. 系统定位

在退赔决策 Agent 的输入输出“AI 治理层”建立主动防御，与工单 5 的沙箱（运行隔离）互补：

- **输入治理**：DLP 对用户材料（OCR 文本）脱敏后再进入 LLM；Critic 对材料做注入/越狱检测。
- **动作治理**：命中“跳过人工审批/直接退款”类危险指令时强制转人工，阻断自动路径。
- **审计治理**：日志、轨迹、Telemetry 只出现掩码文本；原始文本仅存内部库。

## 2. 组件与接口

`backend/app/security/gateway.py`：

- `DLP.mask(text) -> tuple[str, list[str]]`：返回掩码文本与脱敏实体清单。
- `CriticEngine.score(text) -> tuple[float, list[str]]`：返回风险分 0~1 与命中规则。
- `SecurityException`：拦截信号，携带 `risk` 与 `rules`。

## 3. 安全属性

- 确定性优先：规则引擎是唯一拦截事实来源；LLM 增强仅提高召回，失败不影响拦截。
- 不自动放行：命中即人工，无“低风险放行”分支。
- 数据最小化：LLM 材料、日志、观测均使用掩码文本。
- 可审计：命中规则、风险分随工单轨迹与 Langfuse span 留存。
