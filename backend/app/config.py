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
    BCRYPT_ROUNDS: int = 8  # 压测/演示可降低；生产建议 12

    # ===== LLM（OpenAI 兼容适配器）=====
    # LLM_PROVIDER: deepseek | mock   （mock 供本地无密钥 / 单测使用）
    # 本地默认 Mock，避免没有外部密钥时所有订单因保守兜底而转人工；生产环境显式配置 deepseek。
    LLM_PROVIDER: str = "mock"
    DEEPSEEK_API_KEY: str = ""  # 通过 .env 或环境变量注入，严禁硬编码提交
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    PROMPT_VERSION: str = "refund-v1"
    GOLDEN_REPORT_PATH: str = "artifacts/golden-report.json"

    # ===== 决策阈值 =====
    AUTO_REFUND_MAX_AMOUNT: float = 300.0
    FRAUD_SCORE_THRESHOLD: int = 50
    OCR_CONFIDENCE_THRESHOLD: float = 0.6

    # ===== Redis Streams =====
    STREAM_KEY: str = "stream:tickets"
    CONSUMER_GROUP: str = "worker-group"
    CONSUMER_NAME: str = "worker-1"

    # ===== LangGraph Checkpointer =====
    # postgres（默认，零额外依赖） | redis（需 RedisJSON 模块）
    CHECKPOINTER_BACKEND: str = "postgres"
    CHECKPOINTER_TTL_MINUTES: int = 1440   # 挂起上下文在 Redis 的保留时长（默认 24h）

    # ===== 安全网关（Critic 注入检测 + DLP 脱敏，对应 docs/specs/security-gateway.md）=====
    SECURITY_GATEWAY_ENABLED: bool = True
    DLP_ENABLED: bool = True
    DLP_NER_ENABLED: bool = False
    DLP_NER_MODEL_PATH: str = ""
    SECURITY_INJECTION_THRESHOLD: float = 0.85
    SECURITY_LLM_ENHANCE: bool = False   # 可选 LLM 增强，失败不影响规则拦截
    SECURITY_RED_BLUE_REPORT_PATH: str = "artifacts/security-red-blue-report.json"
    SECURITY_DLP_REPORT_PATH: str = "artifacts/security-dlp-report.json"
    SECURITY_AUDIT_REPORT_PATH: str = "artifacts/security-audit-report.json"

    # ===== 工单 8：LLM 重试 / 意图过滤 / 死信队列 =====
    LLM_RETRY_MAX_ATTEMPTS: int = 3      # 首次调用 + 最多 2 次重试
    LLM_RETRY_BASE_DELAY_SECONDS: float = 1.0
    INTENT_FILTER_ENABLED: bool = True   # Node A 确定性意图过滤
    DLQ_STREAM_KEY: str = "stream:tickets:dead"

    # ===== OCR（本地 PaddleOCR）=====
    OCR_DEVICE: str = "cpu"  # cpu | gpu
    OCR_USE_ANGLE_CLS: bool = True
    OCR_LANG: str = "ch"
    OCR_MODEL_DIR: str = ""  # 必须显式配置；模型缺失时禁止隐式下载

    # ===== 文件上传 =====
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_FILES: int = 3
    MAX_UPLOAD_SIZE_MB: int = 10

    # ===== 事件推送 =====
    EVENT_CHANNEL_PREFIX: str = "events:ticket"

    # ===== Telemetry（Langfuse 可选；上报失败不得阻塞业务主流程）=====
    TELEMETRY_ENABLED: bool = False
    TELEMETRY_PROVIDER: str = "noop"   # noop | langfuse
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"
    LANGFUSE_BASE_URL: str = ""        # 兼容旧命名；非空时优先于 LANGFUSE_HOST

    # ===== CubeSandbox（未完整配置时禁止创建远程沙箱）=====
    SANDBOX_PROVIDER: str = "disabled"
    CUBESANDBOX_API_URL: str = "http://127.0.0.1:3000"
    CUBESANDBOX_API_KEY: str = ""
    CUBESANDBOX_TEMPLATE_ID: str = ""
    CUBESANDBOX_PROXY_NODE_IP: str = ""
    CUBESANDBOX_PROXY_PORT: int = 8080


settings = Settings()
