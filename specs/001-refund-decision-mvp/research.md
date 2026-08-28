# Research: 多 Agent 协同客诉舆情退赔决策系统（MVP）

> 上游基线：《需求与技术方案说明书.md》、《核心技术架构深度剖析手册.md》。
> 本文档汇总关键技术决策与取舍，作为后续 `data-model.md`、`contracts/`、`tasks.md` 的依据。

## 决策总览

| # | 主题 | 决策 | 一句话理由 |
| --- | --- | --- | --- |
| 1 | AI 编排 | LangGraph + Redis Checkpointer | 原生中断/恢复，支撑可恢复状态机 |
| 2 | 异步解耦 | FastAPI + Redis Streams + Worker | 长耗时 OCR/LLM 不阻塞 API |
| 3 | 事实与状态分离 | PostgreSQL 权威 + Redis 队列/锁/checkpoint | 可查询审计与可恢复上下文分离 |
| 4 | 凭证识别 | Transformers 中文微调 OCR | 本地推理，输出文字 + 置信度 |
| 5 | 风险/舆情分析 | DeepSeek（OpenAI 兼容） | api_key 云端调用，可替换 |
| 6 | 决策路由 | 无 I/O 纯函数 `decide` | 决策唯一来源，可单测 |
| 7 | 失败兜底 | 重试 → 保守值 → 转人工（宁挂勿错退） | 不确定绝不自动放行 |
| 8 | 防资损 | 幂等三层防线 + SET NX 锁 + 条件更新 | 退款重复即资损 |
| 9 | 认证 | JWT（仅 Access Token，2h） | MVP 最小够用 |
| 10 | 实时展示 | SSE 推送 + 2s 轮询降级 | 断线可恢复 |
| 11 | 部署验证 | Docker Compose + Locust | 一键启动、可压测 |

---

## 1. LangGraph + Redis Checkpointer（可恢复状态机）

- **Decision**: 用 LangGraph 的 `StateGraph` 编排 Agent，注入 `RedisSaver` 作为 Checkpointer；
  挂起走原生 `interrupt()`，恢复走 `Command(resume=...)`。
- **Rationale**: 原生支持「图定义」与「执行状态」分离——图定义编译后不变、放进程内存；
  执行状态外置 Redis，Worker 成为无状态服务，崩溃可恢复、可水平扩容。
- **Alternatives considered**:
  - 手工 `pickle` 图状态：破坏 LangGraph 状态版本兼容与校验，被否决。
  - API 直接 `graph.resume()`：与 Worker 争抢同一 checkpoint 产生竞态，被否决（改为投递 `RESUME` 消息由 Worker 串行恢复）。
- **红线**: 初始执行与恢复必须用同一 Redis 与同一 `thread_id`；不手工 pickle；API 不直接 resume。

## 2. FastAPI + Redis Streams 生产者-消费者（异步长任务）

- **Decision**: API 作为生产者 `XADD` 到 `stream:tickets`；Worker 用消费组 `XREADGROUP` 拉取，
  「先处理后确认」——成功才 `XACK`，异常保留 Pending 供重试/回收，不可恢复错误落库
  `FAILED + error_code` 后再确认。
- **Rationale**: OCR/LLM 为重资源长耗时任务，同步执行会阻塞连接、拖垮 P95；解耦后建单/审批
  接口只返回「已受理」（`202`）。
- **Alternatives considered**:
  - 请求内同步执行模型：P95 不可控，被否决。
  - 简单队列（LPUSH/BRPOP）：缺消费组与 Pending 回收语义，Streams 更合适。

## 3. 事实与状态分离（PostgreSQL vs Redis）

- **Decision**: PostgreSQL 存工单、审批、轨迹等业务事实（可查询、可审计）；Redis 仅承担
  Streams 队列、幂等键、审批锁、LangGraph checkpoint。
- **Rationale**: 业务真相与可恢复执行上下文是不同生命周期的概念；Redis 挂起 checkpoint 丢失
  不得导致业务事实丢失。
- **Alternatives considered**: 以 Redis 为唯一事实来源——重启/淘汰会丢审计，被否决。

## 4. Transformers 中文微调 OCR 凭证识别

- **Decision**: 用 Hugging Face Transformers 加载 VisionEncoderDecoder 类 OCR 模型，默认
  采用中英文微调模型 `priyank-m/m_OCR`（ViT-MAE 编码器 + XLM-RoBERTa 解码器）；单图置信度取
  生成 token 平均 softmax 概率，多图取最小置信度（木桶原则）；阈值 `OCR_CONFIDENCE_THRESHOLD = 0.60`
  可配置。
- **Rationale**: 证据链可信度是自动放行的第一道闸门，证据不足时禁止进入自动决策；本地推理
  避免外网依赖与网络时延。
- **Alternatives considered**:
  - PaddleOCR（PP-OCR）——中文识别更强，但与「Transformers 加载」约束冲突，被否决。
  - 微软官方 TrOCR（英文）——中文识别能力有限，改用中英文微调模型。
- **注意**: `priyank-m/m_OCR` 为社区微调模型，精度取决于训练数据；不达业务精度时需自行微调
  后替换 `ocr_model_name_or_path`。

## 5. DeepSeek LLM（风险/舆情分析）

- **Decision**: `LlmRiskClient` 通过 OpenAI 兼容接口对接 **DeepSeek**
  （`base_url=https://api.deepseek.com`、`model=deepseek-chat`）；`score_fraud(material) -> int`
  与 `classify_sentiment(material) -> RiskLevel`，temperature=0 + 严格 JSON prompt + 解析校验。
- **Rationale**: DeepSeek 为 OpenAI 兼容接口，`api_key` 认证即可调用；接口保持可替换以降低锁定。
- **Alternatives considered**: 本地 Ollama / transformers 本地加载——本地部署复杂度更高，MVP 优先云端 api_key 调用。
- **开放项**: `LLM_API_KEY` 由部署配置注入（不阻塞编码）；复杂推理场景可切换 `deepseek-reasoner`。

## 6. 决策规则下沉为纯函数

- **Decision**: `decision_rules.decide(amount, ocr_confidence, fraud_score, sentiment) -> str`，
  无 I/O；Agent 只做采集与归一化，不做业务判断。
- **Rationale**: 确定性路由是资损/合规关键路径，必须可回归验证。
- **Alternatives considered**: 把路由判断散落在节点——难以单测、易漂移，被否决。

## 7. LLM 输出失败 Fallback 阶梯（宁挂勿错退）

- **Decision**: 失败分类（超时 / 5xx / 非法 JSON / 非法枚举 / 字段缺失）→ 有限重试（≤1 次，
  指数退避）→ 保守值兜底（Fraud→100、Sentiment→HIGH）→ 决策层强制 HUMAN_REVIEW。
- **Rationale**: 模型不确定时只增人工负担，绝不允许错误放行导致资损。
- **Alternatives considered**: 失败即自动通过——资损风险不可接受，被否决。

## 8. 防资损（幂等 + 分布式锁）

- **Decision**: 幂等复合键 `idem:{资源}:{owner}:{client_key}`，三层防线（Redis SET NX + DB
  联合唯一索引 + 重复返回原工单）；审批锁 `SET lock:approve:{ticket_id} {token} NX PX 10000`
  + 比较 token 的 Lua 释放 + 数据库条件更新兜底。
- **Rationale**: 退款重复执行即资损；并发审批即状态错乱。
- **Alternatives considered**: 无 token 的 `DEL` 释放——会误删他人新锁，被否决。

## 9. JWT 认证（仅 Access Token）

- **Decision**: 用户名密码登录返回 Access Token，有效期 2h，无 Refresh Token；RBAC 区分
  `CUSTOMER_SERVICE` / `SUPERVISOR`；数据权限在服务层过滤，不靠前端隐藏。
- **Rationale**: MVP 最小够用，符合「先保守」原则。
- **Alternatives considered**: Refresh Token / SSO——超出 MVP 范围，被否决（见范围外）。

## 10. 实时展示（SSE + 轮询降级）

- **Decision**: Worker 每完成节点/状态切换先落库再发轻量事件；SSE 只推事件提醒，前端收到后
  调详情接口取完整数据；断线后每 2s 轮询，工单 `COMPLETED` 后停止。
- **Rationale**: SSE 内容不作为最终业务事实，避免大屏展示与真实状态漂移。
- **Alternatives considered**: 纯轮询——延迟与负载偏高；纯 SSE——断线无兜底。二者结合最优。

## 11. 部署与验证（Docker Compose + Locust）

- **Decision**: 五服务编排（frontend/api/worker/postgres/redis），Redis 开 AOF，`restart:
  unless-stopped`；Locust 压测「短时核心 API」而非云端 LLM 完整时长。
- **Rationale**: 一键启动 + 可复现压测证据，满足验收基线（QPS≥200/P95<300ms/错误率<0.1%）。
- **Alternatives considered**: 无健康检查的裸启动——强杀后无法 5s 恢复，被否决。
