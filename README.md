# 智能电商售后与风控决策平台

面向消费电子商品交易与售后处理的多 Agent 平台。系统将官方商品目录、顾客自助购物、智能客服、订单退款、确定性风控决策、主管审批与质量评测纳入同一业务闭环，并以权限隔离、幂等控制和可审计证据保障关键动作可追溯。

> **重要边界**：`AUTO_REFUNDED` 表示系统完成了自动退赔决策记录，不会调用真实支付退款接口。商城支付为模拟支付；真实资金处理必须通过独立的支付集成、幂等与补偿流程交付。

## 系统能力

- **电商交易闭环**：官方目录商品同步、搜索与筛选、商品规格、收货地址、购物车、下单、模拟支付、订单查询和退单申请。
- **顾客智能服务**：基于已发布商品、本人订单和售后规则提供带来源依据的对话式服务；支持脱敏上下文、人工转接及个性化偏好的显式授权、查看和删除。
- **退赔辅助决策**：本地 OCR、注入检测与 DLP、风险/舆情分析、确定性规则和 LangGraph 人工中断恢复组成审慎决策链路。
- **主管工作台**：待审工单、订单与售后服务单、流程轨迹、实时监控、政策依据检索（RAG）、评测中心和安全治理看板。
- **质量与治理**：Golden Dataset、编排与 Token 对比评测、红蓝测试、DLP 审计、故障安全降级、Redis 幂等键和审批锁。

## 三类账号与职责

| 账号角色 | 主要工作 | 数据与权限边界 |
| --- | --- | --- |
| 顾客（`customer`） | 浏览商品、管理地址和购物车、下单、模拟支付、查看本人订单与退单、使用智能客服和隐私偏好控制 | 只能访问自己的地址、订单、退单、会话与偏好；不能访问运营、评测和审批数据 |
| 客服（`cs`） | 在服务订单中心处理订单和退单的业务承接 | 进入后台服务订单/退单视图；不拥有主管审批、评测、安全治理和政策检索权限 |
| 主管（`sv`） | 审批高风险或不确定退赔、查看决策轨迹和监控、执行质量复核 | 可访问审批、工单详情、评测、安全治理与政策依据；审批仍受 Redis 锁和数据库条件更新保护 |

演示账号由部署环境初始化，仅用于本地联调。生产环境必须禁用或重置演示账号，并采用受控的身份管理、JWT 密钥和密码策略。

## 业务架构

```text
顾客 Web
  商品目录 -> 购物车/订单 -> 模拟支付 -> 退款申请
       |                         |
       +-> 智能客服（证据检索、隐私授权、人工转接）

客服 Web ---------------------> 服务订单与退单中心
主管 Web ---------------------> 审批 / 监控 / 评测 / 安全治理 / 政策依据
                                      |
React + TypeScript  <->  FastAPI（JWT、RBAC、幂等、文件校验、SSE）
                                      |
                 PostgreSQL <-> Redis Streams / 锁 / Checkpointer
                                      |
             Worker：OCR -> 安全网关 -> 意图 -> 风险/舆情 -> 确定性决策
                                      |
                    自动决策记录 或 LangGraph interrupt 后主管审批恢复
```

### 退赔决策原则

决策规则由代码确定性执行，不由 LLM 覆盖。金额、OCR 置信度、欺诈分和舆情均满足低风险条件时才可记录为自动决策；任一条件不满足、模型超时、结果不合法或安全规则命中时，系统保守地转人工或标记失败。上传的 OCR 文本、投诉内容和提示词材料均视为不可信输入。

## 技术组成

| 层级 | 实现 |
| --- | --- |
| 前端 | React 18、TypeScript、Vite、Ant Design、ECharts |
| API 与持久化 | FastAPI、SQLAlchemy 2、PostgreSQL（含 pgvector） |
| 异步与决策 | Redis Streams、LangGraph、PostgreSQL/Redis Checkpointer |
| 智能能力 | 本地 PaddleOCR、OpenAI 兼容 LLM 适配器、固定维度本地 embedding、RAG |
| 安全 | JWT、bcrypt、RBAC、上传魔数校验、DLP、注入检测、Redis 幂等和审批锁 |
| 质量工程 | Pytest、Vitest、Golden Dataset、红蓝测试、场景 E2E、Docker Compose |

### 技术选型依据

| 领域 | 选型 | 采用原因 |
| --- | --- | --- |
| Web 应用 | React + TypeScript + Vite | 提供类型约束、快速构建和面向顾客/运营双界面的组件化交付能力 |
| 业务 API | FastAPI + Pydantic | 以类型化契约承载认证、订单、售后和评测接口，便于验证与文档化 |
| 业务数据 | PostgreSQL + SQLAlchemy | 保存订单、工单、审批、评测和审计事实，支持事务与显式迁移治理 |
| 消息与协调 | Redis Streams + LangGraph | 将长耗时决策与 HTTP 请求解耦，并支持人工审批中断、恢复和状态追踪 |
| 检索 | pgvector + 本地 embedding 服务 | 为主管提供有来源、可审计的政策原文检索，不以生成内容替代业务规则 |
| 安全控制 | JWT、RBAC、DLP、幂等键与审批锁 | 将身份、数据边界、敏感信息和重复操作控制在服务端，降低越权与重复处理风险 |

## 模型与智能能力方案

| 能力 | 模型或组件 | 职责 | 可靠性与安全边界 |
| --- | --- | --- | --- |
| 凭证识别 | PaddleOCR 2.x | 在本地识别退单图片中的文本并输出置信度 | 模型需显式配置；低置信、空结果或异常一律进入保守处理，不能自动放行 |
| 风险与舆情理解 | OpenAI 兼容 LLM 适配器（可接 DeepSeek 或 Mock） | 生成结构化风险、舆情和客服语义结果 | LLM 不决定金额、退款或审批；超时和非法结果使用安全默认值并转人工 |
| 政策依据检索 | `bge-small-zh-v1.5` + pgvector | 为主管检索政策、规则和评测材料中的相关原文片段 | 仅返回带来源的证据；不可用或无结果不影响审批主链路 |
| 顾客智能客服 | 检索增强服务 + LLM 适配器 | 基于已发布商品、本人订单和售后规则回答咨询 | 上下文经过权限过滤与脱敏；执行型或需人工的问题创建独立客服工单 |
| 离线与测试降级 | 本地 Mock / Stub | 支持无外部密钥的开发、测试和回归验证 | 仅用于开发与测试，不得伪装为生产模型输出 |

模型位置、密钥、服务地址和启用开关均由环境变量注入，不在 README、镜像或代码中写入特定人员或设备的路径信息。

## 项目结构

```text
backend/
  app/
    agents/                 # OCR、安全网关、风险、舆情与确定性决策图
    commerce_*.py           # 商品、购物车、订单与退单领域模型及服务
    customer_assistant/     # 顾客智能客服、偏好与人工转接
    evaluation/             # 评测记录、指标聚合与运行器
    rag/                    # 主管政策依据检索与审计
    security/               # DLP、注入检测与治理摘要
    routers/                # auth、shop、tickets、evaluations 等 API
    worker/                 # 工单消费与商品目录刷新
  migrations/               # 评测、RAG、客服等显式数据库迁移
  tests/
frontend/
  src/pages/                # 商城、订单、售后、审批、评测、安全治理页面
  src/components/           # 顾客与后台壳层、工单与知识依据组件
evals/                      # Golden、意图和评测样本
scripts/                    # Golden、红蓝、场景、商城与客服 E2E 脚本
deploy/
  compose/                  # 单容器生产式 Compose 编排
  single-container/         # API、Worker、数据服务与 Nginx 镜像入口
docs/                       # 架构指南、验收报告、专项设计与运行证据
```

## 快速开始

### 前置条件

- Docker Desktop 与 Docker Compose
- 已准备 PaddleOCR 2.x 识别模型
- 已准备 `bge-small-zh-v1.5` embedding 模型
- Node.js 20+（仅前端本地开发需要）
- Python 3.11+（仅后端本地开发与测试需要）

根目录 `.env` 用于覆盖运行配置。生产部署至少应设置强 JWT 密钥、数据库凭据、模型配置和所需的 LLM 配置；禁止提交真实密钥、设备路径或个人环境信息。

### 单容器部署

该部署镜像包含 PostgreSQL、Redis、API、Worker、目录刷新任务、RAG embedding 服务和 Nginx，对外暴露 `80` 端口。

```powershell
make build
make up
make ps
```

访问 `http://localhost`。停止服务使用：

```powershell
make down
```

通过 `OCR_MODEL_HOST_DIR` 和 `RAG_EMBEDDING_MODEL_HOST_DIR` 为部署环境显式配置模型挂载位置。模型缺失时，OCR/RAG 相关能力必须显式不可用，不能回退到宿主机执行。

### 本地前端开发

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

### 验证

```powershell
make check
make frontend-build
python scripts/evaluate_golden.py
python scripts/run_red_blue_test.py
```

`make check` 执行 Python 编译与后端测试；`make frontend-build` 执行 TypeScript 检查和前端生产构建。评测和安全脚本会将报告输出到 `artifacts/`，应作为发布证据归档。

## 评测与发布门禁

系统将评测作为质量证据，而非业务路由：

- **Golden Dataset**：覆盖低风险、金额边界、OCR 异常、欺诈、舆情、模型失败、幂等和安全输入等场景。
- **编排与成本**：记录确定性意图过滤与 LLM 路由的样本覆盖、Token 对比及异常兜底状态。
- **安全治理**：红蓝测试、DLP 审计和脱敏运行事件只供主管查看，Telemetry 失败不得阻塞审批主流程。
- **人工复核**：主管的改判、审批意见、工单轨迹与命中文档来源构成审计链路；RAG 只提供原文依据，不改变退赔结果。

发布前至少完成后端测试、前端构建、Golden 评测、安全测试和关键 E2E，并保存对应日志。`128` 元订单仅在全部低风险条件满足时自动决策，否则必须给出原因并转人工。

## 生产安全边界

- 所有接口由 JWT 与后端 RBAC 保护；前端路由限制仅用于体验，不能替代后端鉴权。
- 建单与退单要求幂等键，审批采用随机 token 的 Redis 锁与数据库条件更新，避免重复处理。
- PostgreSQL 是业务事实来源；Redis 负责队列、锁、幂等与 Checkpointer，不承担最终业务裁决。
- 评测、RAG 与客服偏好相关表通过显式迁移交付，应用启动不应静默修改生产数据库结构。
- CubeSandbox 未安装或配置不完整时必须显式失败，禁止回退到宿主机执行任意代码。详见 [CubeSandbox 配置说明](docs/guides/cubesandbox.md)。

## 文档索引

- [总体架构与治理方案](docs/guides/architecture.md)
- [产品验收报告](docs/acceptance/2026-09-07-product-acceptance-report.md)
- [电商平台设计](docs/superpowers/specs/2026-09-03-ecommerce-platform-design.md)
- [顾客智能客服设计](docs/superpowers/specs/2026-09-07-consumer-intelligent-customer-service-design.md)
- [主管政策依据 RAG 设计](docs/superpowers/specs/2026-09-06-supervisor-rag-design.md)
- [部署验证报告](docs/evidence/deploy-report.md)
- [周期评测报告](docs/evidence/periodic-eval-report.md)
- [安全审计报告](docs/evidence/security-audit-report.md)

## 开发约定

修改退赔、OCR、审批、RBAC、幂等、评测或沙箱前，请先阅读 [AGENTS.md](AGENTS.md)。该文件定义了确定性决策、安全隔离、异步失败处理、测试和验收要求。
