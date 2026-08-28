# OCR 样本可靠性修复设计

**目标：** 让 `goods128.png` 与 `invoice350.png` 经真实 Docker 上传和 OCR 链路得到可用文本与置信度，不因 Windows 路径或 Paddle 运行时崩溃而被错误降级为人工审批。

## 已确认根因

1. `scripts/scenario_e2e.py` 直接将 Windows 本机绝对路径写入 `image_paths`；Docker Worker 无法访问这些路径。
2. Docker Worker 的 PaddlePaddle 推理初始化触发 `SIGILL`，错误栈定位在 `SelfAttentionFusePass`，OCR 没有稳定输出。
3. `D:\作业\model\models\m_OCR` 包含 `pytorch_model.bin` 与 `config.json`，不是 PaddleOCR 所需的已导出推理模型，排除在本次实现范围之外。

## 范围

- 场景脚本改为通过 `POST /api/tickets/with-files` 提交 multipart 文件，使图片写入 API 与 Worker 共享的 `/data/uploads` volume。
- 场景脚本默认访问 Docker API `http://localhost:8001`。
- Docker 镜像使用 Python 3.11 构建，并重建 API 与 Worker，避免运行旧的 Python 3.12 镜像。
- 添加不依赖真实 OCR 引擎的测试，验证场景脚本使用 multipart 上传且不再提交宿主机绝对路径。
- 用两张固定样本对重建后的 Docker Worker 做真实 OCR 验证。

## 非目标

- 不接入 PyTorch 格式的 `m_OCR` 模型。
- 不降低 `OCR_CONFIDENCE_THRESHOLD=0.6`。
- 不改变 `invoice350.png` 的人工审批结论：金额 350 超出自动退款上限 300。
- 不改变 Docker 内 API 与 Worker 使用的 `/data/uploads` 共享卷。

## 验收标准

1. `scenario_e2e.py` 通过 multipart 向 `/api/tickets/with-files` 上传样本图片，工单只保存 `uploads/<uuid>.png` 存储键。
2. `goods128.png` 在 Docker Worker 中 OCR 返回非空文本和大于 0.6 的置信度；在低风险 Mock 配置下，最终决策为 `AUTO_REFUNDED`。
3. `invoice350.png` 在 Docker Worker 中 OCR 返回非空文本和大于 0.6 的置信度；最终仍因金额为 350 而处于人工审批流程。
4. Docker Worker 日志不包含 `Illegal instruction` / `SIGILL`。
