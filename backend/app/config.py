from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./test.db"
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    STORAGE_PATH: str = "/tmp/weddinglens"
    SECRET_KEY: str = "insecure-dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FRONTEND_URL: str = "http://localhost:3000"
    GUEST_SESSION_IDLE_TTL_SECONDS: int = 86400   # 24 hours
    GUEST_LOCKOUT_ATTEMPTS: int = 3
    GUEST_LOCKOUT_DURATION_SECONDS: int = 900     # 15 minutes
    FACE_SEARCH_SCORE_THRESHOLD: float = 0.4
    FACE_SEARCH_RESULT_CAP: int = 50
    FACE_SEARCH_CACHE_TTL_SECONDS: int = 3600
    APP_HOST: str = "http://localhost:3000"
    # D3 — Sliding-window rate limiter for /search (REQ-17/18, ADR 2026-06-22)
    SEARCH_RATE_LIMIT_MAX: int = 10
    SEARCH_RATE_LIMIT_WINDOW_SECONDS: int = 300  # 5 minutes
    # D4 — Admin processing-failure-rate alerting (REQ-5a/5b/5c, ADR 2026-08-15)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "alerts@weddinglens.example"
    ADMIN_FAILURE_RATE_THRESHOLD: float = 0.10
    ADMIN_FAILURE_RATE_WINDOW_MINUTES: int = 60
    ADMIN_ALERT_DEDUP_MINUTES: int = 60

    @field_validator("DATABASE_URL")
    @classmethod
    def _use_asyncpg_driver(cls, v: str) -> str:
        # Managed Postgres providers (e.g. Railway) inject a bare postgres(ql)://
        # URL, but SQLAlchemy's async engine requires the asyncpg driver scheme.
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v


settings = Settings()
