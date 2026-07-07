from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI-Kiosk Backend"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS & Public Host
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Redis (Local for Kiosk, Upstash for Navigation)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str = "redis://localhost:6379/0"
    UPSTASH_REDIS_REST_URL: str = ""
    UPSTASH_REDIS_REST_TOKEN: str = ""

    # Cloud Vercel App URL
    PUBLIC_WEB_APP_URL: str = ""
    # Public backend URL (ngrok or load-balancer) used as a fallback for direct QR links
    PUBLIC_BASE_URL: str = ""

    # SQLite
    SQLITE_DB_PATH: str = "./data/kiosk.db"

    # PostgreSQL
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/vidyasahayak"

    # Session
    SESSION_TTL_SECONDS: int = 1800  # 30 minutes

    # Service flags (toggle real vs mock)
    USE_MOCK_SERVICES: bool = True
    WHISPER_MODEL_SIZE: str = "base"
    USE_BHASHINI: bool = False
    BHASHINI_USER_ID: str = ""
    BHASHINI_API_KEY: str = ""
    BHASHINI_INFERENCE_KEY: str = ""
    BHASHINI_PIPELINE_ID: str = "64392f96daac500b55c543cd"

    # Entity Resolver
    ENTITY_RESOLVER_DIRECT_THRESHOLD: float = 90.0
    ENTITY_RESOLVER_DISAMBIG_THRESHOLD: float = 85.0
    ENTITY_RESOLVER_DELTA: float = 10.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
