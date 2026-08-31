# Agent 评测可视化验收证据

## 1. 验收范围与环境

- 验收日期：2026-08-31（Asia/Shanghai）。
- 代码分支：`main`。
- Python：`D:\anaconda\envs\refuse_agent\python.exe`，版本 3.11.16。
- 前端运行时：Node.js 24.17.0；Docker 前端构建使用 Node 20 Alpine。
- 验收对象：主管评测中心、单笔成本下钻、评测写入幂等与失败隔离、RBAC、显式迁移、Docker 服务。
- 未下载新依赖、模型或权重。

## 2. 后端、Golden 与前端门禁

### 后端

执行：

```powershell
D:\anaconda\envs\refuse_agent\python.exe -m compileall -q backend scripts
D:\anaconda\envs\refuse_agent\python.exe -m pytest backend/tests -q
D:\anaconda\envs\refuse_agent\python.exe scripts/evaluate_golden.py
```

结果：

- `compileall`：退出码 0，无编译错误。
- 完整后端测试：退出码 0，`86 passed`，0 失败，0 跳过，耗时 7.18 秒。
- 后端产生 100 条 Paddle/protobuf `DeprecationWarning`；属于第三方弃用告警，没有静默忽略失败或跳过测试。
- Golden Dataset：退出码 0，10/10 用例的路由、安全性和解释性均符合预期，总分 30/30，`passed=true`。

补充说明：Codex 受限执行上下文直接启动工作区外的 Conda Python 时曾无输出并返回 1；同一可执行文件在获准环境中返回 Python 3.11.16，随后上述门禁均成功。该现象定位为 Windows 应用沙箱执行权限边界，不是源码编译失败。

### 前端

执行：

```powershell
node --test frontend/tests/*.test.mjs
npm --prefix frontend run build
```

结果：

- UI 契约：退出码 0，10/10 通过，0 失败，0 跳过。
- TypeScript 与 Vite 生产构建：退出码 0，4,684 个模块完成转换。
- 构建产物：CSS 7.38 kB（gzip 2.32 kB）；主 JS 2,383.73 kB（gzip 779.08 kB）。
- Vite 报告大于 500 kB 的 chunk 警告；这是待优化项，不记为测试或构建失败。

## 3. 显式迁移演练

迁移文件：`backend/migrations/20260830_add_agent_evaluation_runs.sql`。

在副本数据库 `refund_eval_migration_20260831085035` 中执行迁移两次：

```powershell
Get-Content backend/migrations/20260830_add_agent_evaluation_runs.sql |
  docker compose exec -T postgres psql -U postgres -d refund_eval_migration_20260831085035 -v ON_ERROR_STOP=1
```

结果：

- 第一次执行退出码 0，`agent_evaluation_runs` 表及唯一/普通索引创建成功。
- 第二次执行退出码 0，证明 `IF NOT EXISTS` 迁移可重复执行。
- 工单数迁移前后保持 40；副本哨兵记录迁移前后保持 1。
- 相同迁移已应用到当前本地 `refund` 数据库；工单数保持 40，评测表存在。
- `init_db()` 已由自动化测试证明不通过 `create_all` 静默创建评测表。

迁移演练副本在证据记录后已精确删除；复核 `pg_database` 命中数为 0。

## 4. Docker 与接口验收

执行：

```powershell
docker compose config --quiet
docker compose build api worker frontend
docker compose up -d --no-deps --force-recreate api worker frontend
docker compose ps api worker frontend postgres redis --format json
docker compose logs --tail 20 worker
```

结果：

- Compose 配置校验退出码 0。
- `agent-api`、`agent-worker`、`agent-frontend` 三个镜像构建退出码 0。
- API、Worker、Frontend 重建并启动；PostgreSQL 与 Redis 为 `healthy`，Worker 输出 `INFO worker started`。
- API `GET /healthz` 返回 200；前端 `GET /evaluations` 返回 200。
- 主管 `GET /api/evaluations/summary` 返回 200；客服同一请求返回 403。
- Golden 报告在主管汇总响应中 `available=true`。
- 使用脱敏验收记录时，主管单笔详情返回 200、`available=true`、总 Token 为 70；客服权限仍被拒绝。
- 验收记录 `acceptance-20260831085447` 已精确执行 `DELETE 1`，复核命中数为 0。清理后单笔详情按空状态契约返回 200、`available=false`。
- 审查修复后再次使用精确标识 `acceptance-review-202608310941` 验收负 Token 变化：主管详情返回 200、`saved_tokens=-10`、`reduction_ratio=-0.25`，并包含 OCR、风控、舆情、决策四个耗时阶段；验收后执行 `DELETE 1`，复核命中数为 0。

Compose 重建时报告 `agent-web-1` 孤儿容器。其标签指向另一个工作目录，未使用 `--remove-orphans` 删除，避免影响无关项目。

## 5. 375×812 浏览器验收

使用 Edge 140 无头模式、Chrome DevTools Protocol 1.3 和真实主管登录态，将设备指标设置为 375×812。审查修复后的自动检查返回：

```json
{
  "summary": {
    "viewport": { "width": 375, "height": 812 },
    "noHorizontalOverflow": true,
    "titleVisible": true,
    "tokenFallbackVisible": true,
    "recentVisible": true,
    "increaseVisible": true,
    "growthVisible": true,
    "goldenVisible": true
  },
  "detail": {
    "noHorizontalOverflow": true,
    "evaluationVisible": true,
    "increaseVisible": true,
    "growthVisible": true,
    "ocrLatencyVisible": true,
    "decisionLatencyVisible": true
  }
}
```

结论：评测中心和工单详情均无整体横向滚动；“Agent 评测中心”标题、Token 精确数值后备、“最近评测记录”、Golden、“增加 10”“增幅 25.0%”以及 OCR/决策耗时均可见。数据表自身保留局部横向滚动，这是窄屏下的预期交互。

前两次一次性验收脚本分别因 `localhost`/`127.0.0.1` Origin 不一致和 Token 字符串多重编码而停留在 `/login`，均退出 1，未记作页面通过；修正脚本后第三次退出 0。临时脚本和专用 Edge 实例已清理。

审查修复后的复验也有两次工具链失败：第一次 Edge 调试端口未保持监听，第二次 CDP 目标未完成导航，均未产生页面断言且未记作通过。改用 Edge 调试接口创建登录页后，最终检查退出 0；临时脚本、专用 Edge 配置与实例均已清理。

## 6. 结论与保留项

本轮可视化范围的后端、Golden、前端、迁移、角色权限、Docker 和 375px 验收均有退出码或接口状态证据。完整测试集覆盖：同一 `run_id` 连续写入最终仅一行；兼容 `resume_action` 消息不写评测；评测持久化返回失败时工单仍按既定结果完成或保持 `SUSPENDED`、人工审批路径不进入失败态；非唯一约束完整性错误显式返回失败；负 Token 变化、Golden 独立空状态和详情随工单刷新重新请求。

保留项：主前端包体积警告尚未处理；真实 CubeSandbox、外部 Telemetry、LLM-as-a-judge、成本币种换算、正式压测，以及 Fraud/Sentiment 图节点并行化与 `parallel_ms` 不属于本轮可视化交付，不能据此文档声称这些方向已完成。当前只记录串行 LangGraph 的 OCR、风控、舆情和决策四个真实阶段。
