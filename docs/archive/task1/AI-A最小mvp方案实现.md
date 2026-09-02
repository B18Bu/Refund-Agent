# AI 驱动审批决策系统 MVP 实现方案

## 一、需求转述（我的理解）

我们要做一个 **AI 驱动的审批决策系统 MVP**，核心包括：

1. **用户与权限**：客服、主管登录；使用 JWT 进行身份认证，不同角色拥有不同的审批权限。
2. **AI 决策流程**：提交审批请求后，系统自动启动由多个 AI 智能体协作完成的决策流，包括 OCR 识别、舆情风控、金额决策；流程基于 LangGraph 编排。
3. **流程可中断**：决策流运行中可以挂起，例如等待人工补充材料。挂起时需保存完整中间状态，恢复后可以从断点继续运行。
4. **防重复提交**：前端每次提交均携带唯一键；后端使用分布式锁，确保同一请求不会被重复处理。
5. **可视化**：大屏可查看各 Agent 的执行路径、OCR 识别文本和舆情风险评分。
6. **可部署、可压测**：通过 Docker Compose 一键启动，使用 Locust 压力测试验证性能。

---

## 二、技术实现方案（从零开始，最小可行 MVP）

### 2.1 整体技术栈建议

| 层次 | 选型 |
| --- | --- |
| 后端框架 | FastAPI（Python，异步支持良好，天然适配 LangGraph） |
| 数据库 | PostgreSQL（存储用户、审批单和流程记录） |
| 缓存 / 状态存储 | Redis（分布式锁、幂等键、序列化挂起的图上下文） |
| AI 编排框架 | LangGraph（原生支持状态持久化与恢复） |
| 认证 | JWT（PyJWT） |
| 容器化 | Docker Compose |
| 压测 | Locust |
| 前端大屏 | 简单 React + ECharts，或 Streamlit（用于快速出图） |

### 2.2 核心模块与类设计（Python 视角）

```text
src/
├── auth/
│   ├── models.py              # User、Role（SQLAlchemy）
│   ├── dependencies.py        # get_current_user、require_role
│   └── jwt_handler.py         # create_token、decode_token
├── approval/
│   ├── models.py              # ApprovalRequest（审批单）
│   ├── schemas.py             # Pydantic 请求 / 响应模型
│   ├── service.py             # 提交、查询、挂起、恢复等业务逻辑
│   └── idempotency.py         # 幂等键检查与分布式锁
├── workflow/
│   ├── graph.py               # LangGraph 图定义：OCR、风控、决策 Agent
│   ├── state.py               # 全局状态定义（TypedDict）
│   ├── agents/
│   │   ├── ocr_agent.py       # 调用 OCR 服务（MVP 可 Mock）
│   │   ├── risk_agent.py      # 舆情风控评分（Mock 或简单 API）
│   │   └── decision_agent.py  # 根据金额阈值和风险分做最终决策
│   └── checkpoint.py          # 与 Redis 交互，保存 / 加载图状态
├── dashboard/
│   ├── routes.py              # 大屏数据 API
│   └── service.py             # 聚合执行路径、OCR 文本、风险分
└── main.py                    # FastAPI 入口
```

### 2.3 数据库表结构（核心表）

#### 用户表：`users`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | 主键（PK） |
| `username` | string | 唯一用户名 |
| `password_hash` | string | bcrypt 密码哈希 |
| `role` | enum | 客服 / 主管 |

#### 审批请求表：`approval_requests`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | 主键（PK） |
| `idempotency_key` | string | 唯一索引，用于防重复提交 |
| `applicant_name` | string | 申请人 |
| `amount` | decimal | 金额 |
| `attachment_url` | string | 附件（图片 / PDF） |
| `status` | enum | `pending` / `running` / `suspended` / `completed` / `rejected` |
| `current_node` | string | 当前所在 Agent 节点名称 |
| `final_result` | JSON | 最终决策结果 |
| `created_at` | timestamp | 创建时间 |
| `updated_at` | timestamp | 更新时间 |

#### 执行轨迹表：`execution_traces`

用于大屏展示工作流执行情况。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID | 主键（PK） |
| `request_id` | UUID | 关联审批请求 |
| `node_name` | string | Agent 名称 |
| `input_data` | JSON | 节点入参 |
| `output_data` | JSON | 节点出参，如 OCR 文本、风险评分等 |
| `start_time` | timestamp | 开始时间 |
| `end_time` | timestamp | 结束时间 |
| `status` | string | `success` / `failed` |

### 2.4 核心流程实现要点

#### 提交审批（防重复）

1. 前端通过 `X-Idempotency-Key` 请求头传入幂等键。
2. 后端通过 Redis `SETNX` 加锁：

   ```text
   key = idempotency:{key}
   TTL = 24h
   ```

3. 成功获取锁后，创建审批单并启动 LangGraph 异步任务。
4. MVP 阶段使用 FastAPI `BackgroundTasks`；后续可按需迁移到 Celery。
5. 接口返回审批单 ID。

#### 决策流（LangGraph）

1. 定义 `GraphState`，至少包含以下字段：

   ```text
   request_id
   ocr_text
   risk_score
   amount
   final_decision
   ```

2. 节点执行顺序：**OCR → 风控 → 金额决策**。
3. 每个节点执行完毕后，将关键输出写入 `execution_traces` 表。
4. 若需挂起，例如金额超过阈值且需要主管人工介入，则在决策节点前抛出 `SuspendedException`：
   - 调用 Redis 保存 `graph.checkpoint`，序列化完整状态；
   - 将审批请求状态更新为 `suspended`。

#### 挂起与恢复

挂起时，将图状态存入 Redis：

```python
redis.set(f"checkpoint:{request_id}", pickle.dumps(graph_state))
```

恢复时：

1. 主管调用恢复接口；
2. 后端从 Redis 反序列化状态；
3. 重新注入 LangGraph，从挂起节点继续执行。

#### 大屏展示

提供接口：

```text
GET /dashboard/trace/{request_id}
```

接口返回：

- 全部节点执行顺序（从 `execution_traces` 查询）；
- OCR 文本（从 OCR 节点的输出获取）；
- 风险分（从风控节点的输出获取）。

前端使用时间线图和信息卡片展示相关内容。

---

## 三、需要决策或澄清的模糊点

| 编号 | 问题 | 影响 |
| --- | --- | --- |
| 1 | OCR Agent 调用真实 OCR 服务（如阿里云、百度），还是 MVP 阶段使用 Mock？ | 真实调用需要外网 API 密钥和计费；建议 MVP 先 Mock，并保留可替换接口。 |
| 2 | 舆情风控 Agent 的数据源是什么？第三方舆情 API，还是内部数据库？ | 决定是否需要外部依赖；MVP 可先采用基于关键词的简单模拟评分。 |
| 3 | 金额决策逻辑是什么？例如“金额大于 10 万且风险分大于 80 则拒绝，否则通过”。 | 需要明确规则，否则无法实现决策 Agent。 |
| 4 | 挂起的触发条件是什么？金额超过阈值、风控分异常，还是所有流程均支持人工挂起？ | 决定挂起逻辑所在节点，以及权限控制方式。 |
| 5 | 挂起后由谁恢复？客服还是主管？恢复时是否需要二次鉴权？ | 影响权限控制设计。 |
| 6 | 大屏采用实时轮询还是 WebSocket 推送？ | MVP 建议采用轮询，但需确认刷新频率要求。 |
| 7 | Locust 压测目标指标是什么？如并发用户数、P95 响应时间、吞吐量。 | 未定义目标则无法判断性能验证是否通过。 |
| 8 | 审批单完成状态是自动决策，还是最终仍需人工点击确认？ | 影响流程终点设计。 |
| 9 | 是否支持多个审批单同时运行，即 LangGraph 是否需要并发执行？ | 影响资源规划和 Redis 连接池配置。 |
| 10 | JWT 的过期时间和刷新策略是什么？ | 影响登录体验和安全性。 |

---

## 四、MVP 交付物清单（建议）

- 数据库 ER 图（3 张核心表）；
- FastAPI 接口文档（Swagger 自动生成）；
- 核心代码：认证、工作流、大屏；
- `docker-compose.yml`（包括 PostgreSQL、Redis、应用服务和前端静态资源）；
- Locust 压测脚本，以及压测报告截图；
- `README.md` 部署说明，包括一键启动命令。
