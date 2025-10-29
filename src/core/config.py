"""Environment configuration for Chatico Mapper App."""

from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class InstagramSettings(BaseModel):
    """Instagram API settings."""

    app_id: str = Field(..., description="Instagram App ID")
    app_secret: str = Field(..., description="Instagram App Secret")
    access_token: str = Field(..., description="Instagram App Access Token")
    api_base_url: str = Field(
        default="https://graph.instagram.com/v23.0",
        description="Instagram API base URL",
    )
    api_timeout: int = Field(
        default=30,
        description="Instagram API timeout (seconds)",
    )


class WebhookSettings(BaseModel):
    """Webhook verification settings."""

    secret: str = Field(..., description="Instagram webhook signing secret")
    verify_token: str = Field(..., description="Webhook verification token")
    max_size: int = Field(
        default=1_048_576,
        description="Maximum webhook payload size in bytes",
    )


class RedisSettings(BaseModel):
    """Redis cache configuration."""

    url: Optional[str] = Field(
        default=None,
        description="Redis connection URL (redis://user:pass@host:port/db)",
    )
    ttl: int = Field(
        default=86_400,
        description="Default cache TTL in seconds (24 hours)",
    )

    @property
    def enabled(self) -> bool:
        """Return True when Redis caching is configured."""
        return bool(self.url)


class Settings(BaseSettings):
    """Application-level settings loaded from environment variables."""

    # Application metadata
    app_name: str = Field(default="Chatico Mapper App")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # HTTP server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)

    # Database (PostgreSQL)
    database_url: str = Field(..., description="Async SQLAlchemy database URL")
    database_pool_size: int = Field(default=20)
    database_max_overflow: int = Field(default=30)

    # Feature toggles / secrets
    secret_key: str = Field(..., description="Application secret key")
    jwt_algorithm: str = Field(default="HS256")
    jwt_expire_minutes: int = Field(default=30)

    # Nested settings
    instagram: InstagramSettings
    webhook: WebhookSettings
    redis: RedisSettings = Field(default_factory=RedisSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",  # Enable INSTAGRAM__APP_ID style variables
        extra="ignore",
    )

    @field_validator("log_level")
    @classmethod
    def normalise_log_level(cls, value: str) -> str:
        """Ensure log level is a valid logging level name."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_value = value.upper()
        if upper_value not in allowed:
            raise ValueError(f"log_level must be one of: {', '.join(sorted(allowed))}")
        return upper_value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Require an async PostgreSQL DSN."""
        valid_prefixes = ("postgresql+asyncpg://", "postgresql://")
        if not value.startswith(valid_prefixes):
            raise ValueError(
                "database_url must start with postgresql+asyncpg:// or postgresql://",
            )
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
