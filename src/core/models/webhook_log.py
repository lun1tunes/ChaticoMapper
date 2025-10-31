"""Webhook Log model for audit trail."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models.base import Base

if TYPE_CHECKING:
    from src.core.models.worker_app import WorkerApp


class WebhookLog(Base):
    """Audit log for webhook processing."""

    __tablename__ = "webhook_logs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    webhook_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False, comment="Unique webhook ID"
    )
    account_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Instagram account ID"
    )
    worker_app_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("worker_apps.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Target worker app ID",
    )
    target_owner_username: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Target Instagram username"
    )
    target_base_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Target base URL"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="Processing status"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Error messages")
    processing_time_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Processing time in milliseconds"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, server_default=func.now()
    )

    # Relationships
    worker_app: Mapped["WorkerApp | None"] = relationship("WorkerApp", back_populates="webhook_logs")

    def __repr__(self) -> str:
        return f"<WebhookLog(id={self.id}, webhook_id={self.webhook_id}, status={self.status})>"
