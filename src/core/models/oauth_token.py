"""OAuth token storage for external providers (e.g., Google/YouTube)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models.base import Base

if TYPE_CHECKING:
    from src.core.models.user import User


class OAuthToken(Base):
    """Encrypted OAuth tokens keyed by provider/account."""

    __tablename__ = "oauth_tokens"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "account_id",
            "user_id",
            name="uq_oauth_provider_account_user",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    provider: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True, comment="OAuth provider identifier"
    )
    account_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="External account identifier (e.g., channel id)",
    )
    encrypted_access_token: Mapped[str] = mapped_column(
        String(2048), nullable=False, comment="Encrypted access token"
    )
    encrypted_refresh_token: Mapped[str | None] = mapped_column(
        String(2048), nullable=True, comment="Encrypted refresh token"
    )
    scope: Mapped[str | None] = mapped_column(
        String(1024), nullable=True, comment="Granted scopes"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Access token expiry time"
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
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of the OAuth credentials",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="oauth_tokens",
    )

    def __repr__(self) -> str:
        return f"<OAuthToken(provider={self.provider}, account_id={self.account_id})>"
