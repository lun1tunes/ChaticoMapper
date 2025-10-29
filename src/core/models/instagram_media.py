"""Instagram Media model for caching media-to-owner mappings."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models.base import Base

if TYPE_CHECKING:
    from src.core.models.instagram_comment import InstagramComment


class InstagramMedia(Base):
    """Cache for Instagram media information to avoid repeated API calls."""

    __tablename__ = "instagram_media"

    media_id: Mapped[str] = mapped_column(
        String(100), primary_key=True, comment="Instagram media ID"
    )
    owner_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Instagram account ID of media owner"
    )
    owner_username: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Instagram username of media owner"
    )
    permalink: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Media permalink URL")
    media_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Media type (IMAGE, VIDEO, CAROUSEL_ALBUM)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    comments: Mapped[list["InstagramComment"]] = relationship(
        "InstagramComment", back_populates="media", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<InstagramMedia(media_id={self.media_id}, owner_id={self.owner_id})>"
