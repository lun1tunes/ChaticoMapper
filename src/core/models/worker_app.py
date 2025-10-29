"""Worker App model for Instagram account to app mapping."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models.base import Base

if TYPE_CHECKING:
    from src.core.models.webhook_log import WebhookLog


class WorkerApp(Base):
    """Worker application configuration for routing Instagram webhooks."""

    __tablename__ = "worker_apps"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        comment="Instagram account ID of the business owner",
    )
    owner_instagram_username: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Instagram username of the account owner",
    )
    base_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Base URL (including path) for forwarding webhooks",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    webhook_logs: Mapped[list["WebhookLog"]] = relationship(
        "WebhookLog",
        back_populates="worker_app",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<WorkerApp(id={self.id}, owner_id={self.owner_id}, "
            f"base_url={self.base_url})>"
        )
