# API Contract: 多 Agent 协同客诉舆情退赔决策系统（MVP）

> 上游基线：《需求与技术方案说明书.md》§11。契约用于前后端对接与测试。

## 认证

JWT（仅 Access Token，有效期 2h）。Payload：

```json
{ "sub": "user_id", "role": "CUSTOMER_SERVICE | SUPERVISOR", "exp": "<2h 后 Unix 时间戳>" }
```

## 接口清单

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | 公开 | 用户名密码登录，返回 Access Token |
| `POST` | `/api/tickets` | 客服/主管 | 创建工单；Header 必须携带 `X-Idempotency-Key` |
| `POST` | `/api/tickets/{id}/files` | 创建人或主管 | multipart 上传图片；最多 3 张 |
| `GET` | `/api/tickets` | 客服/主管 | 客服返回本人，主管返回全部；支持状态筛选/分页 |
| `GET` | `/api/tickets/{id}` | 创建人或主管 | 详情、文件、OCR、风险、决策、轨迹 |
| `GET` | `/api/tickets/{id}/events` | 创建人或主管 | SSE 事件流 |
| `POST` | `/api/tickets/{id}/approval` | 仅主管 | 提交 `APPROVE`/`REJECT`，触发恢复任务 |
| `GET` | `/healthz` | 公开/内网 | API 健康检查 |
| `GET` | `/readyz` | 公开/内网 | DB、Redis 依赖检查 |

## 请求/响应示例

### 登录

```http
POST /api/auth/login
Content-Type: application/json

{"username":"supervisor_01","password":"***"}
```

```json
{"access_token":"eyJ...","token_type":"bearer","expires_in":7200}
```

### 创建工单

```http
POST /api/tickets
Authorization: Bearer <token>
X-Idempotency-Key: 4c4c450c-8fc9-4cb7-8757-982859cbb396
Content-Type: application/json

{"amount":"350.00","complaint_text":"商品破损，申请退款"}
```

```json
{"ticket_id":"t_123","ticket_no":"RF202608170001","status":"RUNNING","outcome":"PENDING"}
```

> 重复调用相同幂等键返回相同 `ticket_id`，不新建工单。

### 上传凭证

```http
POST /api/tickets/t_123/files
Authorization: Bearer <token>
Content-Type: multipart/form-data

files=@invoice.jpg
```

```json
{"ticket_id":"t_123","files":[{"id":"f_001","filename":"invoice.jpg","content_type":"image/jpeg","size_bytes":248102}]}
```

### 主管审批

```http
POST /api/tickets/t_123/approval
Authorization: Bearer <supervisor-token>
Content-Type: application/json

{"action":"APPROVE","comment":"情况属实，批准退款"}
```

```json
{"ticket_id":"t_123","status":"RUNNING","outcome":"PENDING","message":"审批已记录，决策流正在恢复"}
```

> 审批接口返回「恢复已入队」，最终结果通过详情接口/SSE 获得，不承诺同步完成。

## 标准错误语义

| HTTP 状态 | 场景 | 示例错误码 |
| --- | --- | --- |
| `400` | 金额、文件格式、审批动作非法 | `VALIDATION_ERROR` |
| `401` | 未携带/无效/过期 JWT | `UNAUTHORIZED` |
| `403` | 客服审批、越权查看他人工单 | `FORBIDDEN` |
| `404` | 工单不存在或无权限时按安全策略隐藏 | `TICKET_NOT_FOUND` |
| `409` | 已完成工单再审批、并发审批、状态不匹配 | `TICKET_STATE_CONFLICT` |
| `413` | 超过图片数量或体积上限 | `FILE_TOO_LARGE` |
| `415` | 非 JPG/JPEG/PNG | `UNSUPPORTED_MEDIA_TYPE` |
| `422` | 请求体字段不符合约束 | `VALIDATION_ERROR` |
| `503` | Redis/数据库不可用，无法安全入队 | `DEPENDENCY_UNAVAILABLE` |

## 内部消息契约（Redis Streams）

```json
// START：初始执行
{ "type": "START", "ticket_id": "t_123", "thread_id": "lg_t_123", "created_at": "..." }

// RESUME：主管审批后恢复
{ "type": "RESUME", "ticket_id": "t_123", "thread_id": "lg_t_123", "approval_action": "APPROVE", "approval_id": "a_456" }
```

消费组语义：成功完整处理后才 `XACK`；异常不确认（保留 Pending 供重试/回收）；
不可恢复错误更新为 `COMPLETED + FAILED`、记录 `error_code` 后再确认。

## SSE 事件类型

| 事件 | 载荷要点 | 说明 |
| --- | --- | --- |
| `trace_updated` | ticket_id, agent_name, status | 节点轨迹变化 |
| `ticket_status_changed` | ticket_id, status, outcome | 工单状态切换 |
| `completed` | ticket_id, outcome | 工单完成 |

> SSE 只推送事件提醒，前端收到后调用详情接口获取完整可信数据；SSE 内容不作为最终业务事实。
