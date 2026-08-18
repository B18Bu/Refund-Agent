"""本地 OCR 适配器：PaddleOCR 推理引擎。

约束（用户 P0）：OCR 必须在本地自动下载并成功部署 PaddleOCR 推理引擎，
实现真实的本地图片文字识别与置信度计算；禁止远程 OCR 服务。

- 惰性加载模型（首次调用时初始化，避免模块导入即加载重型依赖）。
- 多图置信度取「最小置信度」（木桶原则）。
- 图片损坏/无法识别 → 置信度 0 → 决策层强制人工。
"""
import logging
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OcrResult:
    text: str
    confidence: float


_ocr = None  # 惰性单例，避免 import 即拉取重型依赖


def _get_ocr():
    """惰性初始化 PaddleOCR 引擎（首次调用自动下载模型）。"""
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR  # 延迟导入，测试环境无该依赖也可跑

        _ocr = PaddleOCR(
            use_angle_cls=settings.OCR_USE_ANGLE_CLS,
            lang=settings.OCR_LANG,
            show_log=False,
        )
    return _ocr


class OcrClient:
    """本地 OCR 客户端（可替换接口）。"""

    def extract(self, image_path: str) -> OcrResult:
        try:
            ocr = _get_ocr()
            results = ocr.ocr(image_path, cls=settings.OCR_USE_ANGLE_CLS)
        except Exception as exc:
            logger.warning("OCR 识别失败 %s: %s", image_path, exc)
            return OcrResult(text="", confidence=0.0)

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
