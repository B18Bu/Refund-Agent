"""本地 OCR 适配器：PaddleOCR 推理引擎。

约束（用户 P0）：OCR 必须在本地自动下载并成功部署 PaddleOCR 推理引擎，
实现真实的本地图片文字识别与置信度计算；禁止远程 OCR 服务。

- 惰性加载模型（首次调用时初始化，避免模块导入即加载重型依赖）。
- 多图置信度取「最小置信度」（木桶原则）。
- 图片损坏/无法识别 → 置信度 0 → 决策层强制人工。
"""
import logging
import os
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OcrResult:
    text: str
    confidence: float
    error_code: str | None = None


_ocr = None  # 惰性单例，避免 import 即拉取重型依赖


def _get_ocr():
    """使用显式本地模型惰性初始化 PaddleOCR，禁止隐式下载。"""
    global _ocr
    if _ocr is None:
        model_dirs = {
            "det_model_dir": os.path.join(settings.OCR_MODEL_DIR, "det"),
            "rec_model_dir": os.path.join(settings.OCR_MODEL_DIR, "rec"),
            "cls_model_dir": os.path.join(settings.OCR_MODEL_DIR, "cls"),
        }
        required_files = ("inference.pdmodel", "inference.pdiparams")
        if not settings.OCR_MODEL_DIR or any(
            not os.path.isfile(os.path.join(model_dir, filename))
            for model_dir in model_dirs.values()
            for filename in required_files
        ):
            raise RuntimeError(f"OCR 模型文件不完整: {settings.OCR_MODEL_DIR}")

        # PaddlePaddle 会影响后续 SciPy 扩展的 zlib 初始化，先预加载 SciPy。
        import scipy  # noqa: F401
        from paddle import inference
        from paddleocr import PaddleOCR  # 延迟导入，测试环境无该依赖也可跑

        # PaddleOCR 2.9.1 内部硬编码开启 IR 优化，在部分 AMD Docker 环境触发 SIGILL。
        original_create_predictor = inference.create_predictor

        def create_predictor_without_ir(config):
            config.switch_ir_optim(False)
            return original_create_predictor(config)

        inference.create_predictor = create_predictor_without_ir
        try:
            _ocr = PaddleOCR(
                use_angle_cls=settings.OCR_USE_ANGLE_CLS,
                lang=settings.OCR_LANG,
                show_log=False,
                use_gpu=False,
                enable_mkldnn=False,
                ir_optim=False,
                **model_dirs,
            )
        finally:
            inference.create_predictor = original_create_predictor
    return _ocr


class OcrClient:
    """本地 OCR 客户端（可替换接口）。"""

    def extract(self, image_path: str) -> OcrResult:
        if not os.path.isfile(image_path):
            logger.warning("OCR 输入文件不存在: %s", image_path)
            return OcrResult(text="", confidence=0.0, error_code="OCR_INPUT_NOT_FOUND")
        try:
            ocr = _get_ocr()
            results = ocr.ocr(image_path, cls=settings.OCR_USE_ANGLE_CLS)
        except Exception as exc:
            logger.warning("OCR 识别失败 %s: %s", image_path, exc)
            return OcrResult(text="", confidence=0.0, error_code="OCR_ENGINE_FAILED")

        texts: list[str] = []
        scores: list[float] = []
        for page in results or []:
            for line in page or []:
                try:
                    text, score = line[1][0], line[1][1]
                    texts.append(text)
                    scores.append(score)
                except (IndexError, TypeError):
                    continue
        joined = "\n".join(texts)
        avg = sum(scores) / len(scores) if scores else 0.0
        return OcrResult(text=joined, confidence=round(avg, 4))


def extract_text(image_path: str) -> tuple[str, float]:
    """兼容旧接口：返回 (识别文字, 平均置信度)。"""
    result = OcrClient().extract(image_path)
    return result.text, result.confidence
