# OCR 样本可靠性修复实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让固定样本通过 Docker 的真实上传和 OCR 链路得到有效识别结果，避免 Windows 绝对路径和旧 Docker 镜像导致的零置信度。

**架构：** 场景脚本将图片作为 multipart 文件上传至 `/api/tickets/with-files`，由 API 存入 `/data/uploads` 共享卷，Worker 只接收 `uploads/<uuid>.png` 存储键。Docker API/Worker 从 Python 3.11 基线重建；先做容器内 OCR 冒烟检查，再执行端到端业务回归。

**技术栈：** Python 3.11、FastAPI、PaddleOCR 2.9.1、PaddlePaddle 2.6.2、Docker Compose、pytest。

---

## 文件结构

- 修改：`scripts/scenario_e2e.py` — 样本工单改为 multipart 上传，默认 API 地址改为 Docker `8001`。
- 修改：`backend/tests/test_scenario_e2e.py` — 验证场景脚本不传宿主机绝对路径而是发送 multipart 文件。
- 修改：`backend/Dockerfile` — 保持 Python 3.11 基线并加入可检查的镜像标签说明；不改变现有 OCR 依赖版本。
- 修改：`docker-compose.yml` — 可选地为 API/Worker 添加共同的可复现 build 配置，仅在重建实际需要时修改。
- 新增：`scripts/verify_ocr_samples.py` — 容器内对两张已上传样本输出文本、置信度并以阈值 0.6 校验。

### 任务 1：将场景样本改为真实 multipart 上传

**文件：**
- 修改：`scripts/scenario_e2e.py:16-87`
- 创建：`backend/tests/test_scenario_e2e.py`

- [ ] **步骤 1：编写失败的脚本请求测试**

在 `backend/tests/test_scenario_e2e.py` 写入测试，将 `urllib.request.urlopen` 替换为捕获请求的 stub，调用新建的 `submit_ticket_with_file()`，断言请求地址为 `/api/tickets/with-files`、请求头 `Content-Type` 以 `multipart/form-data; boundary=` 开头、请求体含文件字段和 `amount` 字段，且不含 `D:/Claude Code`：

```python
def test_submit_ticket_with_file_uses_multipart_upload(monkeypatch, tmp_path):
    import scripts.scenario_e2e as scenario

    image = tmp_path / "goods128.png"
    image.write_bytes(b"png-data")
    request = capture_request(monkeypatch)

    scenario.submit_ticket_with_file(128.0, image, "token")

    assert request.full_url.endswith("/api/tickets/with-files")
    assert request.headers["Content-type"].startswith("multipart/form-data; boundary=")
    assert b'name="amount"' in request.data
    assert b'name="files"; filename="goods128.png"' in request.data
    assert b"D:/Claude Code" not in request.data
```

- [ ] **步骤 2：运行测试并确认失败**

运行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/test_scenario_e2e.py::test_submit_ticket_with_file_uses_multipart_upload -v
```

预期：FAIL，提示 `submit_ticket_with_file` 尚未定义。

- [ ] **步骤 3：实现最小 multipart 请求构造**

在 `scripts/scenario_e2e.py` 添加 `submit_ticket_with_file(amount: float, image_path: Path, token: str)`，以随机 boundary 构造二进制 multipart 请求；文件字段名固定为 `files`，金额字段名固定为 `amount`。将场景一和场景二的建单调用替换为这个函数，保留认证和后续状态断言。

```python
def submit_ticket_with_file(amount: float, image_path: Path, token: str):
    boundary = f"----refund-{uuid.uuid4().hex}"
    body = build_multipart_body(boundary, amount, image_path)
    request = urllib.request.Request(
        BASE + "/api/tickets/with-files", data=body, method="POST"
    )
    request.add_header("Authorization", "Bearer " + token)
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(request) as response:
        return response.status, json.loads(response.read().decode())
```

同时将：

```python
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
```

替换为：

```python
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
```

- [ ] **步骤 4：运行测试确认通过**

运行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/test_scenario_e2e.py -v
```

预期：PASS。

- [ ] **步骤 5：提交该任务**

```bash
git add scripts/scenario_e2e.py backend/tests/test_scenario_e2e.py
git commit -m "fix: upload OCR scenario samples through API"
```

### 任务 2：固定 Docker Python 基线并验证镜像运行时

**文件：**
- 修改：`backend/Dockerfile:1-26`
- 测试：Docker 镜像内 `python --version`。

- [ ] **步骤 1：验证当前运行容器的 Python 版本**

运行：

```powershell
docker compose exec -T worker python --version
```

预期：当前旧容器输出 Python 3.12.x，证明正在运行的镜像不对应 `FROM python:3.11-slim`。

- [ ] **步骤 2：添加镜像 Python 基线标识**

在 `backend/Dockerfile` 的基础镜像声明后加入以下注释，明确 OCR 容器需要从此基线重建：

```dockerfile
# OCR 运行时固定 Python 3.11；变更基础版本必须先用 scripts/verify_ocr_samples.py 验证。
```

不得把 PyTorch 格式的 `D:\作业\model\models\m_OCR` 复制或挂载到此镜像，因为它不是 PaddleOCR inference model。

- [ ] **步骤 3：重建 API 与 Worker 镜像**

运行：

```powershell
docker compose build --no-cache api worker
docker compose up -d --force-recreate api worker
```

预期：两个服务被新镜像重新创建。

- [ ] **步骤 4：验证容器运行时 Python 版本**

运行：

```powershell
docker compose exec -T api python --version
docker compose exec -T worker python --version
```

预期：两个容器均输出 `Python 3.11.x`。

- [ ] **步骤 5：提交该任务**

```bash
git add backend/Dockerfile
git commit -m "build: pin OCR containers to Python 3.11"
```

### 任务 3：为固定样本提供容器 OCR 验证脚本

**文件：**
- 创建：`scripts/verify_ocr_samples.py`
- 修改：`README.md` — 增加 Docker OCR 样本验证命令。

- [ ] **步骤 1：编写失败的验证测试**

在 `backend/tests/test_scenario_e2e.py` 中增加测试，通过 monkeypatch 注入返回 `(text, confidence)` 的 OCR 函数，断言 `validate_result()` 在空文本或置信度不高于 0.6 时抛出 `ValueError`：

```python
def test_validate_result_rejects_empty_or_low_confidence():
    from scripts.verify_ocr_samples import validate_result

    with pytest.raises(ValueError, match="识别文本为空"):
        validate_result("", 0.99, "goods128.png")
    with pytest.raises(ValueError, match="低于阈值"):
        validate_result("正品全新商品", 0.6, "goods128.png")
```

- [ ] **步骤 2：运行测试并确认失败**

运行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/test_scenario_e2e.py::test_validate_result_rejects_empty_or_low_confidence -v
```

预期：FAIL，提示 `scripts.verify_ocr_samples` 不存在。

- [ ] **步骤 3：实现验证脚本**

创建 `scripts/verify_ocr_samples.py`，读取两个命令行图片路径并调用 `app.agents.ocr.OcrClient().extract()`。实现：

```python
THRESHOLD = 0.6

def validate_result(text: str, confidence: float, image_name: str) -> None:
    if not text.strip():
        raise ValueError(f"{image_name}: 识别文本为空")
    if confidence <= THRESHOLD:
        raise ValueError(f"{image_name}: 置信度 {confidence} 低于阈值 {THRESHOLD}")
```

每张图片输出其识别文本与置信度；任一校验失败时进程返回非零退出码。

- [ ] **步骤 4：运行测试确认通过**

运行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/test_scenario_e2e.py::test_validate_result_rejects_empty_or_low_confidence -v
```

预期：PASS。

- [ ] **步骤 5：在 Docker Worker 中执行 OCR 样本验证**

先通过真实 multipart 上传使两张样本进入 `/data/uploads`，然后运行：

```powershell
docker compose exec -T worker python /app/scripts/verify_ocr_samples.py /data/uploads/<goods-storage-filename>.png /data/uploads/<invoice-storage-filename>.png
```

预期：两个样本均输出非空文本与大于 0.6 的置信度；Worker 日志不含 `Illegal instruction` 或 `SIGILL`。

- [ ] **步骤 6：提交该任务**

```bash
git add scripts/verify_ocr_samples.py backend/tests/test_scenario_e2e.py README.md
git commit -m "test: add Docker OCR sample verification"
```

### 任务 4：执行端到端业务回归

**文件：**
- 测试：`scripts/scenario_e2e.py`、Docker Compose 运行服务。

- [ ] **步骤 1：以 Mock LLM 重建并启动服务**

运行：

```powershell
$env:LLM_PROVIDER = "mock"
docker compose up -d --build
```

预期：`api`、`worker`、`postgres`、`redis`、`frontend` 都是运行状态。

- [ ] **步骤 2：运行场景脚本**

运行：

```powershell
.\.venv\Scripts\python.exe scripts\scenario_e2e.py http://localhost:8001
```

预期：

```text
[S1] <tid> 挂起 [OK]  OCR置信度=<大于 0.6>
[S1] <tid> APPROVED [OK]
[S2] <tid> AUTO_REFUNDED [OK]  (OCR置信度=<大于 0.6>)
[LOCK] 并发审批 {409:5, 200:1} [OK]
=== 全部场景通过 ===
```

- [ ] **步骤 3：验证端口与 Worker 日志**

运行：

```powershell
Invoke-WebRequest http://localhost:8001/healthz -UseBasicParsing
docker compose logs --since 10m worker
```

预期：健康检查为 HTTP 200；Worker 日志不包含 `Illegal instruction`、`SIGILL`、`OCR 识别失败`。

- [ ] **步骤 4：运行后端回归测试**

运行：

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests -v
```

预期：所有测试通过。

- [ ] **步骤 5：提交验收记录**

```bash
git add docs/superpowers/specs/2026-08-20-ocr-sample-reliability-design.md docs/superpowers/plans/2026-08-20-ocr-sample-reliability.md
git commit -m "docs: record OCR sample reliability verification"
```
