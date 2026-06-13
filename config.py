"""
统一配置管理 —— 所有凭据和参数从 .env 读取
优先级：环境变量 > .env 文件 > 默认值
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 数据库 ──
    DATABASE_URL: str = "mysql+pymysql://root:123456@127.0.0.1:3306/standard_ai?charset=utf8mb4"

    # ── DeepSeek ──
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ── Embedding ──
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    HF_ENDPOINT: str = "https://hf-mirror.com"
    EMBEDDING_SIMILARITY_THRESHOLD: float = 0.25

    # ── 日志 ──
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/app.log"

    # ── CORS ──
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ── JWT ──
    JWT_SECRET: str = "change-me-in-production-use-a-long-random-string-here"
    JWT_EXPIRE_HOURS: int = 24

    # ── 应用 ──
    APP_TITLE: str = "智能标准文档管理与RAG问答系统"
    UPLOAD_DIR: str = "uploads"


settings = Settings()
