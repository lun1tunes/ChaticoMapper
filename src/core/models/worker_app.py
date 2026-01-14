"""Worker App model for Instagram account to app mapping."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models.base import Base

if TYPE_CHECKING:
    from src.core.models.user import User
    from src.core.models.webhook_log import WebhookLog


class WorkerApp(Base):
    """Worker application configuration for routing Instagram webhooks."""

    __tablename__ = "worker_apps"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    base_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Base URL (including path) for forwarding webhooks",
    )
    webhook_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Webhook endpoint URL for forwarding requests",
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Associated application user",
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
    user: Mapped["User | None"] = relationship("User", back_populates="worker_apps")
    webhook_logs: Mapped[list["WebhookLog"]] = relationship(
        "WebhookLog",
        back_populates="worker_app",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<WorkerApp(id={self.id}, base_url={self.base_url}, "
            f"webhook_url={self.webhook_url}, user_id={self.user_id})>"
        )
