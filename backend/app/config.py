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


settings = Settings()
