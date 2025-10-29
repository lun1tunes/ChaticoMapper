"""Database models for Chatico Mapper App."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class WorkerApp(Base):
    """Worker application configuration model."""

    __tablename__ = "worker_apps"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    owner_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Instagram account ID",
    )
    app_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Application name for identification"
    )
    base_url: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Base URL for HTTP requests"
    )
    webhook_path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="/webhook",
        comment="Webhook path (default: /webhook)",
    )
    queue_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Queue name for RabbitMQ routing"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Active status flag"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Created timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Updated timestamp",
    )

    # Relationships
    webhook_logs: Mapped[list["WebhookLog"]] = relationship(
        "WebhookLog",
        back_populates="worker_app",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("idx_worker_apps_owner_id_active", "owner_id", "is_active"),
        Index("idx_worker_apps_queue_name", "queue_name"),
    )


class WebhookLog(Base):
    """Webhook processing log model."""

    __tablename__ = "webhook_logs"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    webhook_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique webhook ID",
    )
    owner_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Instagram account ID"
    )
    worker_app_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("worker_apps.id"),
        nullable=True,
        index=True,
        comment="Target worker app ID",
    )
    target_app_name: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Target app name"
    )
    processing_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Processing status (success/failed/routed)",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Error messages"
    )
    processing_time_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="Processing time in milliseconds"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
        comment="Created timestamp",
    )

    # Relationships
    worker_app: Mapped[Optional["WorkerApp"]] = relationship(
        "WorkerApp",
        back_populates="webhook_logs",
    )

    # Indexes
    __table_args__ = (
        Index("idx_webhook_logs_owner_status", "owner_id", "processing_status"),
        Index("idx_webhook_logs_created_at", "created_at"),
        Index(
            "idx_webhook_logs_worker_app_status", "worker_app_id", "processing_status"
        ),
    )
