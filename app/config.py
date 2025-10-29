"""Environment configuration for Chatico Mapper App."""

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Redis
    redis_url: Optional[str] = Field(default=None, description="Redis URL for caching")
    redis_ttl: int = Field(default=3600, description="Redis TTL in seconds")

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

    # Instagram API
    instagram_app_id: str = Field(..., description="Instagram App ID")
    instagram_app_secret: str = Field(..., description="Instagram App Secret")
    instagram_access_token: str = Field(..., description="Instagram Access Token")
    instagram_api_base_url: str = Field(
        default="https://graph.instagram.com", description="Instagram API base URL"
    )
    instagram_api_timeout: int = Field(
        default=30, description="Instagram API timeout in seconds"
    )
    instagram_rate_limit: int = Field(
        default=200, description="Instagram API rate limit per hour"
    )

    # Webhook Security
    webhook_secret: str = Field(..., description="Webhook verification secret")
    webhook_verify_token: str = Field(..., description="Webhook verification token")
    webhook_max_size: int = Field(
        default=1048576, description="Max webhook payload size (1MB)"
    )

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

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v):
        """Validate Redis URL."""
        if v is not None and not v.startswith(("redis://", "rediss://")):
            raise ValueError("Redis URL must start with redis:// or rediss://")
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Global settings instance
settings = Settings()
