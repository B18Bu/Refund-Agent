# Implementation Plan: 多 Agent 协同客诉舆情退赔决策系统（MVP）

**Branch**: `001-refund-decision-mvp` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-refund-decision-mvp/spec.md`

## Summary

构建一个多 Agent 协同的客诉退赔辅助决策系统 MVP：客服提交工单（金额、描述、凭证图片）后，
系统通过异步任务编排自动执行「凭证识别 → 风险分析 → 舆情分析 → 金额决策」链路，对低风险
工单自动给出退赔结论，对高风险/不确定工单挂起并转主管人工审批。技术方案采用
FastAPI + Redis Streams 生产者-消费者解耦长耗时任务，LangGraph + Redis Checkpointer 实现
可恢复状态机，PostgreSQL 作为业务事实唯一来源，Transformers 中文微调 OCR 做凭证识别，
DeepSeek 做风险与舆情分析，前端 React + ECharts 大屏实时展示决策过程。核心红线是「宁挂勿错退」
与「幂等 + 互斥」双重防资损。

## Technical Context

**Language/Version**: Python 3.11（后端）+ TypeScript 5.x（前端）

**Primary Dependencies**: FastAPI、LangGraph（`langgraph-checkpoint-redis`）、Transformers、
SQLAlchemy、PyJWT、redis-py、OpenAI 兼容客户端（DeepSeek）；React、TypeScript、ECharts

**Storage**: PostgreSQL（工单/审批/轨迹等业务事实）、Redis（Streams 队列、幂等键、分布式锁、
LangGraph Checkpointer）、本地文件卷（凭证图片）

**Testing**: pytest（单元 + 集成）、Locust（压测）

**Target Platform**: Linux 容器（Docker Compose 编排）

**Project Type**: web-service（前后端分离：FastAPI API + React 前端 + 独立 Worker）

**Performance Goals**: 核心短时 API QPS ≥ 200、P95 < 300ms、错误率 < 0.1%

**Constraints**: API 短请求不同步执行 OCR/LLM；Redis 非业务事实唯一来源；分布式锁须
token + Lua 释放；模型不确定不自动放行；API 不直接恢复 LangGraph

**Scale/Scope**: 2 角色（客服/主管）、5 张核心表、MVP 单机可演示、Worker 可横向扩容

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 设计要求 | 状态 |
| --- | --- | --- |
| I. API 短请求、Worker 长任务 | 建单/审批只校验+落库+投递，返回 `202`；OCR/LLM 由 Worker 异步消费 | ✅ 满足 |
| II. 业务事实与图状态分离 | PostgreSQL 存业务事实；Redis 仅队列/锁/幂等/checkpoint | ✅ 满足 |
| III. 先保守、后自动 | 任一不确定（OCR<0.60/超时/非法输出）转人工，绝不自动放行 | ✅ 满足 |
| IV. 决策规则可测试 | 路由下沉为无 I/O 纯函数 `decision_rules.decide`，单测覆盖 | ✅ 满足 |
| V. 幂等与互斥缺一不可 | 建单幂等键三层防线；审批 SET NX PX + 比较 token 的 Lua 释放 + 条件更新 | ✅ 满足 |
| VI. 审计可回放 | `agent_traces` 记录节点输入/输出/审批/错误码，不落敏感凭据 | ✅ 满足 |

实现红线（不可违反，设计已全部规避）：

1. ✅ 不在 API 请求中同步执行 OCR/LLM（异步 Worker）。
2. ✅ 不把 Redis 当作业务事实唯一来源（PostgreSQL 权威）。
3. ✅ 不用无 token 的 `DEL` 释放锁（Lua 比较 token 后删除）。
4. ✅ 不让异常/模型不确定触发自动通过（保守兜底转人工）。
5. ✅ 不绕过 Worker 由 API 直接恢复 LangGraph（只投递 `RESUME` 消息）。
6. ✅ 不把「记录退款决策」误实现为「调用真实支付退款」（仅落决策结果）。

**结论**: 无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/001-refund-decision-mvp/
├── plan.md              # 本文件
├── research.md          # Phase 0 输出：技术决策
├── data-model.md        # Phase 1 输出：数据模型
├── quickstart.md        # Phase 1 输出：验证指南
├── contracts/           # Phase 1 输出：接口契约
│   └── api.md
└── tasks.md             # Phase 2 输出（/speckit-tasks，本命令不生成）
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── config.py              # 集中配置（DB/Redis/JWT/模型/阈值/文件限制）
│   ├── db.py                  # SQLAlchemy 会话与引擎
│   ├── models.py              # ORM 实体（users/tickets/ticket_files/approvals/agent_traces）
│   ├── schemas.py             # Pydantic 请求/响应模型
│   ├── security.py            # 密码哈希 + JWT 签发/验签
│   ├── deps.py                # 依赖注入 + RBAC
│   ├── redis_client.py        # Redis 客户端
│   ├── idempotency.py         # 建单幂等
│   ├── locks.py               # 审批分布式锁（token + Lua）
│   ├── storage.py             # 文件受控命名/保存/校验
│   ├── agents/
│   │   ├── state.py           # GraphState
│   │   ├── decision_rules.py  # 无 I/O 纯函数路由（决策唯一来源）
│   │   ├── ocr.py             # Transformers OCR（中文微调）封装
│   │   ├── llm.py             # DeepSeek 客户端 + 结构化输出校验
│   │   ├── nodes.py           # 各 Agent 节点（只写状态增量）
│   │   └── graph.py           # build_graph()
│   ├── services/
│   │   ├── ticket_service.py
│   │   ├── approval_service.py
│   │   ├── trace_service.py
│   │   └── event_service.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── tickets.py
│   │   └── files.py
│   └── worker/
│       └── consumer.py        # Redis Streams 消费者 + 图驱动
└── tests/
    ├── unit/                  # decision_rules、幂等、锁、LLM 解析兜底
    └── integration/           # 建单/审批/并发/E2E

frontend/
├── src/
│   ├── pages/Login.tsx
│   ├── pages/Dashboard.tsx
│   ├── pages/TicketDetail.tsx
│   ├── components/FlowCanvas.tsx
│   ├── components/ApprovePanel.tsx
│   └── api/client.ts
└── tests/

docker-compose.yml             # frontend/api/worker/postgres/redis
locustfile.py                  # 压测脚本
```

**Structure Decision**: 采用前后端分离的 web-service 结构。后端 FastAPI 与独立 Worker 进程
共享 `app/` 代码，通过 Redis Streams 解耦；前端 React 通过 Nginx 反向代理 `/api`。
目录结构沿用基线《需求与技术方案说明书.md》§8.1 的既定布局。

## Complexity Tracking

> 无违规项，无需记录。
