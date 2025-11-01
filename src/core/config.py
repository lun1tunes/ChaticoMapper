"""Environment configuration for Chatico Mapper App."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class AppSettings(BaseModel):
    name: str = Field(
        default_factory=lambda: os.getenv("APP_NAME", "Chatico Mapper App").strip()
        or "Chatico Mapper App"
    )
    version: str = Field(
        default_factory=lambda: os.getenv("APP_VERSION", "0.1.0").strip() or "0.1.0"
    )
    debug: bool = Field(default_factory=lambda: _bool_env("DEBUG", False))
    log_level: str = Field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").strip().upper()
    )

    @model_validator(mode="after")
    def _validate(self) -> "AppSettings":
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                "LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL"
            )
        return self


class ServerSettings(BaseModel):
    host: str = Field(
        default_factory=lambda: os.getenv("HOST", "0.0.0.0").strip() or "0.0.0.0"
    )
    port: int = Field(default_factory=lambda: _int_env("PORT", 8000))


class DatabaseSettings(BaseModel):
    url: str = Field(default_factory=lambda: os.getenv("DATABASE_URL", "").strip())
    pool_size: int = Field(default_factory=lambda: _int_env("DATABASE_POOL_SIZE", 20))
    max_overflow: int = Field(
        default_factory=lambda: _int_env("DATABASE_MAX_OVERFLOW", 30)
    )

    @model_validator(mode="after")
    def _validate(self) -> "DatabaseSettings":
        if not self.url:
            raise ValueError("DATABASE_URL environment variable must be set.")
        if not self.url.startswith(
            ("postgresql://", "postgresql+asyncpg://", "sqlite+aiosqlite://")
        ):
            raise ValueError(
                "DATABASE_URL must start with postgresql://, postgresql+asyncpg://, or sqlite+aiosqlite://"
            )
        return self


class InstagramSettings(BaseModel):
    app_secret: str = Field(
        default_factory=lambda: os.getenv("INSTAGRAM_APP_SECRET", "").strip()
    )
    api_base_url: str = Field(
        default_factory=lambda: os.getenv(
            "INSTAGRAM_API_BASE_URL", "https://graph.instagram.com/v23.0"
        ).strip()
    )
    verify_token: str = Field(
        default_factory=lambda: os.getenv("WEBHOOK_INIT_VERIFY_TOKEN", "").strip()
    )

    @model_validator(mode="after")
    def _validate(self) -> "InstagramSettings":
        if not self.app_secret:
            raise ValueError("INSTAGRAM_APP_SECRET environment variable must be set.")
        if not self.verify_token:
            raise ValueError("WEBHOOK_VERIFY_TOKEN environment variable must be set.")
        return self


class RedisSettings(BaseModel):
    url: Optional[str] = Field(
        default_factory=lambda: os.getenv("REDIS_URL", "").strip() or None
    )
    ttl: int = Field(default_factory=lambda: _int_env("REDIS_TTL", 86_400))

    @property
    def enabled(self) -> bool:
        return bool(self.url)


class SecuritySettings(BaseModel):
    secret_key: str = Field(
        default_factory=lambda: os.getenv("JWT_SECRET_KEY", "").strip()
    )

    @model_validator(mode="after")
    def _validate(self) -> "SecuritySettings":
        if not self.secret_key:
            raise ValueError("JWT_SECRET_KEY environment variable must be set.")
        return self


class JWTSettings(BaseModel):
    algorithm: str = Field(
        default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256"
    )
    expire_minutes: int = Field(
        default_factory=lambda: _int_env("JWT_EXPIRE_MINUTES", 30)
    )


class Settings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    instagram: InstagramSettings = Field(default_factory=InstagramSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)

    model_config = dict(extra="ignore")

    # Compatibility helpers -------------------------------------------------
    @property
    def app_name(self) -> str:
        return self.app.name

    @property
    def app_version(self) -> str:
        return self.app.version

    @property
    def debug(self) -> bool:
        return self.app.debug

    @property
    def log_level(self) -> str:
        return self.app.log_level

    @property
    def host(self) -> str:
        return self.server.host

    @property
    def port(self) -> int:
        return self.server.port

    @property
    def database_url(self) -> str:
        return self.database.url

    @property
    def database_pool_size(self) -> int:
        return self.database.pool_size

    @property
    def database_max_overflow(self) -> int:
        return self.database.max_overflow

    @property
    def secret_key(self) -> str:
        return self.security.secret_key

    @property
    def jwt_algorithm(self) -> str:
        return self.jwt.algorithm

    @property
    def jwt_expire_minutes(self) -> int:
        return self.jwt.expire_minutes

    @property
    def redis_url(self) -> Optional[str]:
        return self.redis.url

    @property
    def redis_ttl(self) -> int:
        return self.redis.ttl

    @property
    def redis_enabled(self) -> bool:
        return self.redis.enabled


@lru_cache
def get_settings() -> Settings:
    return Settings()
