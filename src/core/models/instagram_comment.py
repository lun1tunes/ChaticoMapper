"""Instagram Comment model for storing webhook comment data."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models.base import Base

if TYPE_CHECKING:
    from src.core.models.instagram_media import InstagramMedia


class InstagramComment(Base):
    """Instagram comment data from webhooks."""

    __tablename__ = "instagram_comments"

    comment_id: Mapped[str] = mapped_column(
        String(100), primary_key=True, comment="Instagram comment ID"
    )
    media_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("instagram_media.media_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Instagram media ID",
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Comment author's Instagram user ID"
    )
    username: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Comment author's Instagram username"
    )
    text: Mapped[str] = mapped_column(Text, nullable=False, comment="Comment text content")
    parent_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True, comment="Parent comment ID for replies"
    )
    timestamp: Mapped[int] = mapped_column(
        nullable=False, comment="Unix timestamp from webhook entry"
    )
    raw_webhook_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, comment="Raw webhook payload for audit"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    media: Mapped["InstagramMedia"] = relationship("InstagramMedia", back_populates="comments")

    @property
    def comment_datetime(self) -> datetime:
        """Convert Unix timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp)

    @property
    def is_reply(self) -> bool:
        """Check if this is a reply to another comment."""
        return self.parent_id is not None

    def __repr__(self) -> str:
        return f"<InstagramComment(comment_id={self.comment_id}, username={self.username})>"
