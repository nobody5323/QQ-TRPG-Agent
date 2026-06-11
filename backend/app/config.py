"""ChronicleAgent 全局配置"""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """应用配置，优先级：环境变量 > .env 文件 > 默认值"""

    # ── 应用基础 ──
    APP_NAME: str = "ChronicleAgent"
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]

    # ── PostgreSQL ──
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "chronicle"
    DB_PASSWORD: str = "chronicle_secret"
    DB_NAME: str = "chronicle"

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """用于 Alembic 等同步工具"""
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # ── Redis ──
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_MAX_MEMORY: str = "128mb"

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ── LLM ──
    LLM_PROVIDER: str = "openai"  # openai | anthropic | deepseek
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    # ── Embedding ──
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536

    # ── 向量存储 ──
    VECTOR_STORE: str = "qdrant"  # qdrant | pgvector
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # ── RAG ──
    RAG_TOP_K: int = 10
    RAG_SCORE_THRESHOLD: float = 0.5

    # ── 消息 ──
    MESSAGE_CONTEXT_SIZE: int = 20  # 消息处理时携带的最近消息数

    # ── QQ Bot ──
    KP_QQ: str = ""                        # KP 的 QQ 号
    BOT_QQ: str = ""                       # Bot 自身的 QQ 号
    NAPCAT_WS_URL: str = "ws://napcat:8080"  # NapCatQQ WebSocket 地址

    # ── 观�