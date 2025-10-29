"""Environment configuration for Chatico Mapper App."""

from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class InstagramSettings(BaseModel):
    """Instagram API settings."""

    app_id: str = Field(..., description="Instagram App ID")
    app_secret: str = Field(..., description="Instagram App Secret")
    access_token: str = Field(..., description="Instagram Access Token")
    api_base_url: str = Field(
        default="https://graph.instagram.com/v23.0", description="Instagram API base URL"
    )
    api_timeout: int = Field(default=30, description="Instagram API timeout in seconds")
    rate_limit: int = Field(default=200, description="Instagram API rate limit per hour")


class WebhookSettings(BaseModel):
    """Webhook security settings."""

    secret: str = Field(..., description="Webhook verification secret (app_secret)")
    verify_token: str = Field(..., description="Webhook verification token")
    max_size: int = Field(default=1048576, description="Max webhook payload size (1MB)")


class RedisSettings(BaseModel):
    """Redis cache settings."""

    url: Optional[str] = Field(default=None, description="Redis URL for caching")
    ttl: int = Field(default=86400, description="Redis TTL in seconds (24 hours)")


class Settings(BaseSettings):
    """Application settings."""

    # Application
    app_name: str = Field(default="Chatico Mapper App", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="INFO", description="Log level")

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # Database
    database_url: str = Field(..., description="PostgreSQL database URL")
    database_pool_size: int = Field(
        default=20, description="Database connection pool size"
    )
    database_max_overflow: int = Field(default=30, description="Database max overflow")

    # Nested settings
    instagram: InstagramSettings
    webhook: WebhookSettings
    redis: RedisSettings

    # RabbitMQ
    rabbitmq_url: str = Field(..., description="RabbitMQ connection URL")
    rabbitmq_exchange: str = Field(
        default="webhook_router", description="RabbitMQ exchange name"
    )
    rabbitmq_dead_letter_exchange: str = Field(
        default="webhook_router_dlx", description="RabbitMQ dead letter exchange"
    )
    rabbitmq_message_ttl: int = Field(
        default=86400, description="Message TTL in seconds (24 hours)"
    )
    rabbitmq_max_retries: int = Field(default=5, description="Max retry attempts")

    # Security
    secret_key: str = Field(..., description="Application secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expire_minutes: int = Field(default=30, description="JWT expiration in minutes")

    # Monitoring
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, description="Metrics server port")

    # Rate Limiting
    rate_limit_requests: int = Field(
        default=100, description="Rate limit requests per minute"
    )
    rate_limit_window: int = Field(
        default=60, description="Rate limit window in seconds"
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v):
        """Validate database URL."""
        if not v.startswith(
            ("postgresql://", "postgresql+asyncpg://", "sqlite+aiosqlite://")
        ):
            raise ValueError(
                "Database URL must start with postgresql://, postgresql+asyncpg://, or sqlite+aiosqlite://"
            )
        return v

    @field_validator("rabbitmq_url")
    @classmethod
    def validate_rabbitmq_url(cls, v):
        """Validate RabbitMQ URL."""
        if not v.startswith(("amqp://", "amqps://")):
            raise ValueError("RabbitMQ URL must start with amqp:// or amqps://")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",  # Allow INSTAGRAM__APP_ID format
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
