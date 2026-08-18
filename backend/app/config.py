"""应用配置：pydantic-settings，全部可被环境变量覆盖。

对齐三方基线（2026-08-17）：
- LLM：OpenAI 兼容客户端适配器（默认 DeepSeek，可切换 Mock/Stub）。
- OCR：本地 PaddleOCR 推理引擎（MVP 硬性要求，禁止远程 OCR 服务）。
- 决策阈值 / 锁 / Streams 配置统一收敛于此。
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"  # development | testing | production

    # ===== 存储 =====
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/refund"
    REDIS_URL: str = "redis://localhost:6379/0"

    # ===== 认证 =====
    JWT_SECRET: str = "dev-secret-change-me-please-use-a-32-byte-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 120

    # ===== LLM（OpenAI 兼容适配器）=====
    # LLM_PROVIDER: deepseek | mock   （mock 供本地无密钥 / 单测使用）
    LLM_PROVIDER: str = "deepseek"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ===== 决策阈值 =====
    AUTO_REFUND_MAX_AMOUNT: float = 300.0
    FRAUD_SCORE_THRESHOLD: int = 50
    OCR_CONFIDENCE_THRESHOLD: float = 0.6

    # ===== Redis Streams =====
    STREAM_KEY: str = "stream:tickets"
    CONSUMER_GROUP: str = "worker-group"
    CONSUMER_NAME: str = "worker-1"

    # ===== OCR（本地 PaddleOCR）=====
    OCR_DEVICE: str = "cpu"  # cpu | gpu
    OCR_USE_ANGLE_CLS: bool = True
    OCR_LANG: str = "ch"
    OCR_MODEL_DIR: str = ""  # 留空则使用 PaddleOCR 默认自动下载模型

    # ===== 文件上传 =====
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_FILES: int = 3
    MAX_UPLOAD_SIZE_MB: int = 10

    # ===== 事件推送 =====
    EVENT_CHANNEL_PREFIX: str = "events:ticket"


settings = Settings()
