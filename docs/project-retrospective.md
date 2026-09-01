# 项目总结与 AI 编程复盘（工单 5）

> 日期：2026-08-31

## 1. 完成了什么

围绕工单 5（Agent 评测、成本优化与本地沙箱安全协作系统），本期落地：

- **评测与成本**：10 条 Golden Dataset + 确定性三维评测（正确性/安全/解释），
  Token 压缩基线 64.4%（≥30% 达标）；新增可选的 LLM-as-a-judge（DeepSeek 可用时启用）。
- **可观测性**：Langfuse 公共 API 适配器（Basic 认证、脱敏、非阻塞后台队列），
  trace_id 从 Worker 传播到图状态、数据库与 Langfuse。
- **性能**：Fraud/Sentiment 由串行节点重构为 `asyncio.gather(return_exceptions=True)`
  并行风险节点，保留各自 token usage 与耗时。
- **部署**：Docker 栈重建（api/worker/frontend 最新代码），100 用户压测与容灾演练记录。
- **范围调整**：沙箱部分因环境无法部署整体推迟，护栏保留（见方案文档 1.1）。

## 2. 未达标与缺口（如实记录）

- 压测 P95 410ms，未达 300ms 合格线（QPS 370 与 0 错误达标）。
- Langfuse 密钥返回 401，需核对 host/密钥；当前上报已暂时关闭。
- `docker kill` 不触发重启策略（显式停止语义）；崩溃退出自动重启机制已单独验证。
- 沙箱推迟，Word/Excel 文件处理红线不验收。

## 3. 复盘：AI 协作过程中的经验

### 3.1 依赖冲突要“先探测再接入”

接入 Langfuse SDK 时，其 opentelemetry/protobuf(>=5) 与本地 PaddleOCR 的
protobuf(<=3.20.2) 直接冲突。最初尝试降级 OTel 全家桶，仍因 SpanFlags 等
新 API 不兼容而失败；最终改用 Langfuse 公共 REST API，绕开整个依赖树。
教训：第三方 SDK 的传递依赖与本地重型依赖（Paddle）冲突时，优先评估
“官方 REST API + 自有队列”方案，而不是在版本矩阵里打地鼠。

### 3.2 性能结论必须跑在目标部署形态上

本地单进程 API 在 100 并发下连接池被打爆（500），一度误以为系统性能不达标；
切换到 compose 4-worker 后 0 错误。压测环境必须与验收形态一致，否则结论失真。

### 3.3 Docker 语义要实测，不能想当然

原以为 `docker kill` 会触发 restart 策略，实测被当作显式停止；容器内 `kill -9 1`
因 PID 1 受内核保护也无效。最后用独立容器验证“崩溃退出→自动重启”机制。
运维类结论一律以实测为准。

### 3.4 防“氛围编程”的检查点

每次声明“完成”前，用命令产出证据（pytest 数量、golden 报告、压测原始输出、
docker ps/healthz），并记录未达标项，避免把“配置了”说成“验证了”。
