# AI 代码安全与敏感数据泄露审计报告（工单 6）

> 日期：2026-08-31；范围：backend/ 与 scripts/ 全部 Python 代码。

## 1. 危险代码审计（防御性编程）

检查项：`eval()` / `exec()` / `os.system()` / `shell=True` / `subprocess` 危险调用 / 命令拼接。

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| Python `eval()` | 1 处 | `backend/app/locks.py` 的 `redis.eval` 是 Redis 服务端 Lua（锁释放），不执行用户输入 |
| Python `exec()` | 0 | - |
| `os.system()` | 0 | - |
| `shell=True` / 命令拼接 | 0 | 全仓无 shell 调用（AGENTS.md 护栏一致） |
| `subprocess` 危险调用 | 0 | - |

结论：无将用户输入拼接至代码执行路径的漏洞。

## 2. 用户输入路径与 PII 泄露点

| 输入路径 | 处理 | 审计结论 |
| --- | --- | --- |
| 上传文件 | MIME + 魔数 + 重命名 + sha256（storage.py） | 无执行风险 |
| OCR 文本 → LLM | 新增 DLP 掩码（`masked_ocr_text`）后进入 fraud/sentiment 材料 | 已修复（明文不再进模型） |
| OCR 文本 → 日志/轨迹 | Worker 轨迹 summary 经 DLP 掩码 | 已修复 |
| OCR 文本 → Telemetry/Langfuse | `sanitize_payload` 剔除 `ocr_text`/`raw_text` | 不泄露 |
| OCR 文本 → 内部库（tickets.ocr_text） | 保留原文 | 仅内部审计用途，供客服核实凭证；不随日志/观测外发 |
| 注入/越狱输入 | Critic 检测，命中强制人工（`security_injection_detected`） | 新增防线已生效 |

## 3. 脱敏覆盖率验证

- DLP 正则覆盖：手机号 / 身份证 / 银行卡 / API Key / 邮箱。
- 红蓝对抗：100 样本 DLP 漏报率 0%、误报率 0%（详见 `security-red-blue-report.md`）。
- 安全网关单测：10 项全过（`test_security_gateway.py`）。

## 4. 结论

未发现可被利用的代码执行漏洞；用户 PII 在 LLM、日志、轨迹、观测四条路径上均已脱敏；
注入/越狱输入由 Critic 网关拦截并强制人工，不改变审批语义。
