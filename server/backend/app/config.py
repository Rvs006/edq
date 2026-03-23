"""Application configuration from environment variables."""

from pydantic_settings import BaseSettings
from typing import List
import os

# Load .env file manually first to override system env vars
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), override=True)


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "EDQ"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"

    # Database — defaults to SQLite for standalone mode
    DATABASE_URL: str = "sqlite+aiosqlite:///./edq.db"

    # JWT
    JWT_SECRET: str = "change-me-jwt-secret-use-openssl-rand-hex-64"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8080"]

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    REPORT_DIR: str = "./reports"
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB

    # Agent
    AGENT_API_KEY_LENGTH: int = 64
    AGENT_HEARTBEAT_TIMEOUT: int = 300  # 5 minutes

    # AI Synopsis (optional — configure with your preferred LLM provider)
    AI_API_KEY: str = ""
    AI_API_URL: str = ""
    AI_MODEL: str = "gpt-4o"
    AI_MAX_SYNOPSIS_PER_HOUR: int = 10

    # Tools Sidecar
    TOOLS_SIDECAR_URL: str = "http://localhost:8001"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Logging
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.REPORT_DIR, exist_ok=True)
