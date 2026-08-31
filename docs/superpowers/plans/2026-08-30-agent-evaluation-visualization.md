# Agent 评测与 Token 优化可视化实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为主管增加全局 Agent 评测中心和单笔工单评测详情，用可审计数据展示三维评分、Token 数值/降幅和阶段耗时。

**架构：** 新增独立评测表和确定性评测服务，由 Worker 在首次 START 流程完成或挂起前以失败隔离方式写入；主管 API 提供汇总与详情，React 页面用 Ant Design 和 ECharts 展示。现有退赔规则、JWT/RBAC、审批锁和 RESUME 流程保持不变。

**技术栈：** Python 3.11、FastAPI、SQLAlchemy、PostgreSQL、LangGraph、pytest、React 18、TypeScript、Ant Design 5、ECharts。

---

## 文件结构

- 创建 `backend/migrations/20260830_add_agent_evaluation_runs.sql`：显式、可重复执行的 PostgreSQL 建表迁移。
- 创建 `backend/app/evaluation/{__init__,models,scoring,repository,schemas}.py`：评测记录、计算、持久化和响应结构。
- 创建 `backend/app/routers/evaluations.py`：主管汇总接口。
- 修改 `backend/app/agents/{llm,state,nodes}.py`：传播 usage 和阶段耗时，不改变业务值。
- 修改 `backend/app/worker/consumer.py`：START 运行生成幂等 run_id，失败隔离写评测。
- 修改 `backend/app/main.py`、`backend/app/config.py`、`docker-compose.yml`：注册路由并只读挂载 Golden 报告。
- 创建/修改后端专项测试：模型 usage、评分、Worker 幂等、RBAC、汇总与降级。
- 创建 `frontend/src/pages/Evaluations.tsx`、`frontend/src/components/EvaluationDetail.tsx`、`frontend/src/types/evaluation.ts`：全局页、下钻区和类型。
- 修改 `frontend/src/{App.tsx,styles.css}`、`frontend/src/components/AppShell.tsx`、`frontend/src/pages/TicketDetail.tsx`：主管入口、路由、详情与响应式样式。
- 创建 `frontend/tests/evaluation-ui.test.mjs`：无新增依赖的 UI 契约测试。

### 任务 1：评测表与显式迁移

**文件：**
- 创建：`backend/migrations/20260830_add_agent_evaluation_runs.sql`
- 创建：`backend/app/evaluation/__init__.py`
- 创建：`backend/app/evaluation/models.py`
- 修改：`backend/app/models.py`
- 测试：`backend/tests/test_evaluation_model.py`

- [x] **步骤 1：写失败测试，证明 run_id 唯一且评测与工单关联**

```python
import pytest
from sqlalchemy.exc import IntegrityError
from app.evaluation.models import AgentEvaluationRun

def test_evaluation_run_is_unique_per_start(db_session):
    first = AgentEvaluationRun(ticket_id=1, run_id="thread-1:start", prompt_version="refund-v2", provider="mock", measurement_type="estimated", evaluation_status="PASSED")
    db_session.add(first)
    db_session.commit()
    db_session.add(AgentEvaluationRun(ticket_id=1, run_id="thread-1:start", prompt_version="refund-v2", provider="mock", measurement_type="estimated", evaluation_status="PASSED"))
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [x] **步骤 2：运行红灯**

运行：`D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests/test_evaluation_model.py -q`
预期：FAIL，`app.evaluation.models` 不存在。

- [x] **步骤 3：实现模型和迁移**

模型必须包含规格中的 Token、三维评分、`latency_breakdown`、脱敏摘要和错误码；`run_id` 建唯一索引，`ticket_id` 外键带普通索引。SQL 使用 `CREATE TABLE IF NOT EXISTS` 和 `CREATE UNIQUE INDEX IF NOT EXISTS`，不得修改现有表字段。

- [x] **步骤 4：运行绿灯并检查 SQL**

运行：`D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests/test_evaluation_model.py -q`
预期：PASS。

- [x] **步骤 5：提交**

```powershell
git add backend/migrations/20260830_add_agent_evaluation_runs.sql backend/app/evaluation backend/app/models.py backend/tests/test_evaluation_model.py
git commit -m "feat: 添加Agent评测记录模型"
```

### 任务 2：Token usage 与确定性评分

**文件：**
- 修改：`backend/app/agents/llm.py`
- 修改：`backend/app/agents/state.py`
- 修改：`backend/app/agents/nodes.py`
- 创建：`backend/app/evaluation/scoring.py`
- 测试：`backend/tests/test_llm_usage.py`
- 测试：`backend/tests/test_evaluation_scoring.py`

- [x] **步骤 1：写 usage 与评分失败测试**

```python
import pytest

def test_token_delta_keeps_negative_savings():
    from app.evaluation.scoring import calculate_token_delta
    result = calculate_token_delta(baseline_input=40, current_input=50)
    assert result.saved_tokens == -10
    assert result.reduction_ratio == pytest.approx(-0.25)

def test_safety_score_is_zero_when_redline_was_auto_refunded():
    from app.evaluation.scoring import score_evaluation
    score = score_evaluation(amount=350, ocr_confidence=.95, fraud_score=10, sentiment="LOW", actual_route="AUTO_REFUND", reasons=["金额"])
    assert score.safety == 0
```

- [x] **步骤 2：运行红灯**

运行：`D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests/test_llm_usage.py backend/tests/test_evaluation_scoring.py -q`
预期：FAIL，评分模块和 usage 结构不存在。

- [x] **步骤 3：最小实现**

新增不可变 `UsageSnapshot(input_tokens, output_tokens, total_tokens, measurement_type)`；真实供应商从 `response.usage` 读取，Mock 使用现有统一估算器并标记 `estimated`。Fraud/Sentiment 节点把 usage 字典及 `time.perf_counter()` 计算的毫秒数写入 GraphState；业务返回值和保守兜底保持原样。`score_evaluation()` 只调用 `decide_with_reasons` 和确定性字段，不调用模型。

- [x] **步骤 4：运行专项与既有异步测试**

运行：`D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests/test_llm_usage.py backend/tests/test_evaluation_scoring.py backend/tests/test_async_risk.py backend/tests/test_decision_rules.py -q`
预期：全部 PASS。

- [x] **步骤 5：提交**

```powershell
git add backend/app/agents/llm.py backend/app/agents/state.py backend/app/agents/nodes.py backend/app/evaluation/scoring.py backend/tests/test_llm_usage.py backend/tests/test_evaluation_scoring.py
git commit -m "feat: 记录Agent Token与确定性评分"
```

### 任务 3：Worker 失败隔离与幂等落库

**文件：**
- 创建：`backend/app/evaluation/repository.py`
- 修改：`backend/app/worker/consumer.py`
- 测试：`backend/tests/test_worker_evaluation.py`

- [x] **步骤 1：写失败测试**

```python
from app.evaluation.repository import should_record_evaluation, try_persist_evaluation

def test_resume_does_not_create_evaluation():
    assert should_record_evaluation("RESUME") is False
    assert should_record_evaluation("START") is True

def test_evaluation_failure_is_isolated():
    def fail():
        raise RuntimeError("db down")
    assert try_persist_evaluation(fail) is False
```

- [x] **步骤 2：运行红灯**

运行：`D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests/test_worker_evaluation.py -q`
预期：FAIL，持久化钩子不存在。

- [x] **步骤 3：实现单点接入**

START 使用确定性 `run_id=f"{thread_id}:start"`；`should_record_evaluation()` 只允许 START，在决策完成或挂起分支调用一次 repository。repository 捕获唯一键冲突并视为幂等命中；`try_persist_evaluation()` 捕获观测写入异常、记录中文警告并返回 `False`，不得调用 `mark_failed`。RESUME 分支不调用评测服务。

- [x] **步骤 4：运行绿灯与 Graph 回归**

运行：`D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests/test_worker_evaluation.py backend/tests/test_graph.py backend/tests/test_scenario_e2e.py -q`
预期：全部 PASS。

- [x] **步骤 5：提交**

```powershell
git add backend/app/evaluation/repository.py backend/app/worker/consumer.py backend/tests/test_worker_evaluation.py
git commit -m "feat: 接入Worker评测观测副本"
```

### 任务 4：主管汇总与单笔评测 API

**文件：**
- 创建：`backend/app/evaluation/schemas.py`
- 创建：`backend/app/routers/evaluations.py`
- 修改：`backend/app/routers/tickets.py`
- 修改：`backend/app/main.py`
- 修改：`backend/app/config.py`
- 修改：`docker-compose.yml`
- 测试：`backend/tests/test_evaluation_api.py`

- [x] **步骤 1：写 RBAC、空状态和汇总失败测试**

```python
from app.models import Role, User
from app.security import hash_password

def login(client, db_session, username, role):
    db_session.add(User(username=username, password_hash=hash_password("secret123"), role=role))
    db_session.commit()
    response = client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    return response.json()["access_token"]

def auth(token):
    return {"Authorization": f"Bearer {token}"}

def test_customer_cannot_read_evaluation(client, db_session):
    token = login(client, db_session, "cs-eval", Role.CS)
    assert client.get("/api/evaluations/summary", headers=auth(token)).status_code == 403

def test_supervisor_gets_empty_summary_without_fake_points(client, db_session):
    token = login(client, db_session, "sv-eval", Role.SV)
    body = client.get("/api/evaluations/summary", headers=auth(token)).json()
    assert body["evaluation_count"] == 0
    assert body["trend"] == []
```

- [x] **步骤 2：运行红灯**

运行：`D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests/test_evaluation_api.py -q`
预期：FAIL，新接口返回 404。

- [x] **步骤 3：实现接口与 Golden 报告降级**

`GET /api/evaluations/summary` 只聚合有值记录，分别返回数据完整度；从 `GOLDEN_REPORT_PATH` 读取只读报告，文件缺失返回 `{available:false}`。`GET /api/tickets/{id}/evaluation` 无记录返回 HTTP 200 和 `{available:false,status:"NOT_AVAILABLE"}`。Compose 只读挂载 `./artifacts:/app/artifacts:ro`，不上传原始材料。

- [x] **步骤 4：运行 API 与权限回归**

运行：`D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests/test_evaluation_api.py backend/tests/test_tickets_api.py backend/tests/test_auth.py -q`
预期：全部 PASS。

- [x] **步骤 5：提交**

```powershell
git add backend/app/evaluation/schemas.py backend/app/routers/evaluations.py backend/app/routers/tickets.py backend/app/main.py backend/app/config.py docker-compose.yml backend/tests/test_evaluation_api.py
git commit -m "feat: 提供主管评测查询接口"
```

### 任务 5：主管评测中心页面

**文件：**
- 创建：`frontend/src/types/evaluation.ts`
- 创建：`frontend/src/pages/Evaluations.tsx`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/components/AppShell.tsx`
- 修改：`frontend/src/styles.css`
- 创建：`frontend/tests/evaluation-ui.test.mjs`

- [x] **步骤 1：写失败的 UI 契约测试**

```javascript
test('评测中心必须是主管路由并显示真实数据来源', () => {
  assert.match(read('App.tsx'), /path="\/evaluations".*SupervisorOnly/s)
  const page = read('pages/Evaluations.tsx')
  assert.match(page, /measurement_type/)
  assert.match(page, /暂无评测数据/)
  assert.doesNotMatch(page, /64\.4/)
})
```

- [x] **步骤 2：运行红灯**

运行：`node --test frontend/tests/evaluation-ui.test.mjs`
预期：FAIL，页面和路由不存在。

- [x] **步骤 3：实现页面**

复用现有 `client`、`SupervisorOnly`、Ant Design 和 ECharts：四个 KPI、前后柱状图、7 日实线/虚线趋势、三维评分、Golden 独立卡片和最近记录。API 失败显示 Alert+重试；空数组显示 Empty；表格行支持 Enter；图表下提供可见数值摘要。侧栏使用现有图标库并延续已修复的导航前景色继承。

- [x] **步骤 4：运行 UI 契约和构建**

运行：`node --test frontend/tests/ui-layout.test.mjs frontend/tests/evaluation-ui.test.mjs`
运行：`npm --prefix frontend run build`
预期：测试和构建均成功；只允许现有大包体积警告。

- [x] **步骤 5：提交**

```powershell
git add frontend/src/types/evaluation.ts frontend/src/pages/Evaluations.tsx frontend/src/App.tsx frontend/src/components/AppShell.tsx frontend/src/styles.css frontend/tests/evaluation-ui.test.mjs
git commit -m "feat: 添加主管Agent评测中心"
```

### 任务 6：工单评测与成本下钻

**文件：**
- 创建：`frontend/src/components/EvaluationDetail.tsx`
- 修改：`frontend/src/pages/TicketDetail.tsx`
- 修改：`frontend/src/styles.css`
- 修改：`frontend/tests/evaluation-ui.test.mjs`

- [ ] **步骤 1：增加失败测试**

```javascript
test('工单评测详情仅为主管请求并保留审批区', () => {
  const detail = read('pages/TicketDetail.tsx')
  assert.match(detail, /user\?\.role === 'sv'.*EvaluationDetail/s)
  assert.match(detail, /ApprovePanel/)
  assert.match(read('components/EvaluationDetail.tsx'), /评测暂不可用|暂无评测数据/)
})
```

- [ ] **步骤 2：运行红灯**

运行：`node --test frontend/tests/evaluation-ui.test.mjs`
预期：FAIL，`EvaluationDetail` 不存在。

- [ ] **步骤 3：实现下钻组件**

主管详情加载 `/tickets/{id}/evaluation`；展示基线输入、当前输入、输出/总 Token、可为负的节省量、三维依据、阶段耗时、Prompt 版本和来源标签。失败/缺失只影响本卡片；原审批卡片继续渲染和操作。640px 以下单列，数值不只靠颜色表达。

- [ ] **步骤 4：运行绿灯和完整前端构建**

运行：`node --test frontend/tests/ui-layout.test.mjs frontend/tests/evaluation-ui.test.mjs`
运行：`npm --prefix frontend run build`
预期：全部成功。

- [ ] **步骤 5：提交**

```powershell
git add frontend/src/components/EvaluationDetail.tsx frontend/src/pages/TicketDetail.tsx frontend/src/styles.css frontend/tests/evaluation-ui.test.mjs
git commit -m "feat: 展示单笔工单评测成本"
```

### 任务 7：完整门禁、迁移演练与 Docker 验收

**文件：**
- 修改：`docs/agent评测优化方案.md`（只更新本功能完成状态和验证证据）
- 创建：`docs/evidence/agent-evaluation-visualization.md`

- [ ] **步骤 1：运行完整后端门禁**

运行：`D:\anaconda\envs\refuse_agent\python.exe -m compileall -q backend scripts`
运行：`D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests -q`
运行：`D:\anaconda\envs\refuse_agent\python.exe scripts/evaluate_golden.py`
预期：无跳过、无失败，Golden 10/10 通过。

- [ ] **步骤 2：运行完整前端门禁**

运行：`node --test frontend/tests/*.test.mjs`
运行：`npm --prefix frontend run build`
预期：全部成功；记录 bundle warning，但不得描述为测试失败。

- [ ] **步骤 3：在副本数据库演练迁移**

运行：`Get-Content backend/migrations/20260830_add_agent_evaluation_runs.sql | docker compose exec -T postgres psql -U postgres -d refund_test`
预期：首次和第二次执行均成功，现有表数据不变。禁止先在生产库直接运行。

- [ ] **步骤 4：重建服务并做角色验收**

运行：`docker compose build api worker frontend`
运行：`docker compose up -d --no-deps --force-recreate api worker frontend`
验证：主管能访问 `/evaluations` 和单笔评测；客服接口返回 403；评测异常时审批仍可用；375px 无横向页面滚动。

- [ ] **步骤 5：记录证据并提交**

`docs/evidence/agent-evaluation-visualization.md` 必须记录命令、退出码、测试数量、Golden 结果、迁移两次结果、主管/客服 HTTP 状态和浏览器尺寸；任何未执行项目明确标为未验证。

```powershell
git add docs/agent评测优化方案.md docs/evidence/agent-evaluation-visualization.md
git commit -m "docs: 记录Agent评测可视化验收证据"
```

## 完成判定

- 主管双入口、真实/估算标签、Token 数值和百分比、三维评分、趋势与空状态全部可用。
- 客服无法访问评测数据；评测失败不影响工单决策和人工审批。
- START 幂等、RESUME 不重复、负节省量和 Golden 分区均有回归测试。
- 显式迁移完成副本演练；完整后端测试、Golden、沙箱拒绝测试和前端构建有新鲜日志。
