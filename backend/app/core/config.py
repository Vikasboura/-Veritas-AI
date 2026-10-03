"""
app/core/config.py
──────────────────
Central settings via pydantic-settings. All tuneable parameters live here;
no magic constants scattered through business logic.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── API / Auth ──────────────────────────────────────────────────────────
    SECRET_KEY: str = "citebase-pro-secret-key-32-chars-long-production-grade"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000"

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///citebase.db"
    DATABASE_SYNC_URL: str = "sqlite:///citebase.db"

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ── LLM ──────────────────────────────────────────────────────────────────
    LLM_BASE_URL: str = "http://localhost:20128/v1"
    LLM_API_KEY: str = "sk-placeholder"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_JUDGE_MODEL: str = "gpt-4o"
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_TOKENS: int = 2048

    # ── Embeddings / Reranker ─────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_ENABLED: bool = True

    # ── Retrieval ─────────────────────────────────────────────────────────────
    RETRIEVAL_TOP_K_VECTOR: int = 20
    RETRIEVAL_TOP_K_FTS: int = 20
    RETRIEVAL_TOP_N_RERANK: int = 5
    RETRIEVAL_RRF_K: int = 60
    REFUSAL_CONFIDENCE_THRESHOLD: float = 0.35
    HYBRID_ENABLED: bool = True

    # ── Semantic Cache ────────────────────────────────────────────────────────
    CACHE_SIMILARITY_THRESHOLD: float = 0.92
    CACHE_TTL_SECONDS: int = 3600

    # ── PII ───────────────────────────────────────────────────────────────────
    PII_REDACT: bool = False

    # ── Upload ────────────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: str = "pdf,docx,md,txt"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── PulseWatch ───────────────────────────────────────────────────────────
    PULSEWATCH_ENABLED: bool = False
    PULSEWATCH_API_KEY: str = ""

    # ── Eval ─────────────────────────────────────────────────────────────────
    EVAL_JUDGE_MODEL: str = "gpt-4o"

    # ── MCP ──────────────────────────────────────────────────────────────────
    MCP_API_KEY: str = "changeme-mcp-api-key"

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {e.strip().lower() for e in self.ALLOWED_EXTENSIONS.split(",") if e.strip()}

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str | None) -> str:
        if not v:
            return "sqlite+aiosqlite:///citebase.db"
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and "+asyncpg" not in v:
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("DATABASE_SYNC_URL", mode="before")
    @classmethod
    def assemble_sync_db_url(cls, v: str | None) -> str:
        if not v:
            return "sqlite:///citebase.db"
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+psycopg2://", 1)
        if v.startswith("postgresql://") and "+psycopg2" not in v:
            return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached singleton — import this everywhere instead of constructing Settings()."""
    return Settings()  # type: ignore[call-arg]
