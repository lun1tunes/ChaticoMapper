"""Pydantic schemas for Chatico Mapper App."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.core.models.user import UserRole
from src.core.utils.time import now_utc

# =============================================================================
# Webhook payload schemas (copied from instachatico-app)
# =============================================================================


class WebhookVerification(BaseModel):
    """Webhook verification challenge from Instagram."""

    hub_mode: Literal["subscribe"] = Field(..., description="Must be 'subscribe' for verification")
    hub_challenge: str = Field(..., min_length=1, description="Challenge string to echo back")
    hub_verify_token: str = Field(..., min_length=1, description="Verification token")


class CommentAuthor(BaseModel):
    """Instagram user who created the comment."""

    id: str = Field(..., min_length=1, description="Instagram user ID")
    username: str = Field(..., min_length=1, max_length=30, description="Instagram username")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Ensure username doesn't contain invalid characters."""
        if not v.replace(".", "").replace("_", "").isalnum():
            raise ValueError("Username contains invalid characters")
        return v.lower()


class CommentMedia(BaseModel):
    """Instagram media (post) associated with the comment."""

    id: str = Field(..., min_length=1, description="Instagram media ID")
    media_product_type: Optional[str] = Field(None, description="Media product type (e.g., 'FEED', 'REELS')")


class CommentValue(BaseModel):
    """Comment data from Instagram webhook."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    from_: CommentAuthor = Field(..., alias="from", description="Comment author")
    media: CommentMedia = Field(..., description="Associated media")
    id: str = Field(..., min_length=1, description="Comment ID")
    parent_id: Optional[str] = Field(None, description="Parent comment ID for replies")
    text: str = Field(..., min_length=1, max_length=2200, description="Comment text")

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Ensure text is not empty after stripping."""
        if not v.strip():
            raise ValueError("Comment text cannot be empty")
        return v

    def is_reply(self) -> bool:
        """Check if this comment is a reply to another comment."""
        return self.parent_id is not None

    def is_from_user(self, username: str) -> bool:
        """Check if comment is from a specific user."""
        return self.from_.username.lower() == username.lower()


class CommentChange(BaseModel):
    """Change notification from Instagram webhook."""

    field: Literal["comments"] = Field(..., description="Field that changed (must be 'comments')")
    value: CommentValue = Field(..., description="Comment data")


class WebhookEntry(BaseModel):
    """Entry in Instagram webhook payload."""

    id: str = Field(..., min_length=1, description="Instagram business account ID")
    time: int = Field(..., gt=0, description="Unix timestamp of the event")
    changes: List[CommentChange] = Field(..., min_length=1, description="List of changes")

    @field_validator("time")
    @classmethod
    def validate_timestamp(cls, v: int) -> int:
        """Ensure timestamp is reasonable (not too old, not in future)."""
        now = int(datetime.now(timezone.utc).timestamp())
        if v > now + 3600:
            raise ValueError("Timestamp is too far in the future")
        if v < now - 86400 * 7:
            raise ValueError("Timestamp is too old")
        return v

    def get_timestamp(self) -> datetime:
        """Convert Unix timestamp to datetime object."""
        return datetime.fromtimestamp(self.time)


class WebhookPayload(BaseModel):
    """Instagram webhook payload."""

    model_config = ConfigDict(str_strip_whitespace=True)

    entry: List[WebhookEntry] = Field(..., min_length=1, description="List of entries")
    object: Literal["instagram"] = Field(..., description="Object type (must be 'instagram')")

    def get_all_comments(self) -> List[tuple[WebhookEntry, CommentValue]]:
        """Extract all comments from the payload with their entry context."""
        comments: List[tuple[WebhookEntry, CommentValue]] = []
        for entry in self.entry:
            for change in entry.changes:
                if change.field == "comments":
                    comments.append((entry, change.value))
        return comments


# =============================================================================
# Routing responses
# =============================================================================


class RoutingResponse(BaseModel):
    """Webhook routing response schema."""

    status: str = Field(..., description="Processing status")
    message: str = Field(..., description="Response message")
    routed_to: Optional[str] = Field(None, description="Target owner username")
    processing_time_ms: Optional[int] = Field(
        None, description="Processing time in milliseconds"
    )
    error_details: Optional[str] = Field(None, description="Error details if any")
    webhook_id: str = Field(..., description="Unique webhook ID")


# =============================================================================
# Worker app schemas
# =============================================================================


class WorkerAppCreate(BaseModel):
    """Worker app creation schema."""

    account_id: str = Field(
        ..., description="Instagram account ID", min_length=1, max_length=255
    )
    owner_instagram_username: str = Field(
        ..., description="Instagram username of the owner", min_length=1, max_length=255
    )
    base_url: AnyHttpUrl = Field(..., description="Base URL for HTTP requests")


class WorkerAppUpdate(BaseModel):
    """Worker app update schema."""

    owner_instagram_username: Optional[str] = Field(
        None, description="Instagram username of the owner", min_length=1, max_length=255
    )
    base_url: Optional[AnyHttpUrl] = Field(None, description="Base URL for HTTP requests")


class WorkerAppResponse(BaseModel):
    """Worker app response schema."""

    id: UUID = Field(..., description="Worker app ID")
    account_id: str = Field(..., description="Instagram account ID")
    owner_instagram_username: str = Field(
        ..., description="Instagram username of the owner"
    )
    base_url: str = Field(..., description="Base URL for HTTP requests")
    created_at: datetime = Field(..., description="Created timestamp")
    updated_at: datetime = Field(..., description="Updated timestamp")

    model_config = ConfigDict(from_attributes=True)


class WorkerAppListResponse(BaseModel):
    """Worker app list response schema."""

    items: List[WorkerAppResponse] = Field(..., description="List of worker apps")
    total: int = Field(..., description="Total count")
    page: int = Field(..., description="Current page")
    size: int = Field(..., description="Page size")


# =============================================================================
# Monitoring responses
# =============================================================================


class MetricsResponse(BaseModel):
    """Metrics response schema."""

    webhook_total: int = Field(..., description="Total webhooks processed")
    webhook_success: int = Field(..., description="Successful webhooks")
    webhook_failed: int = Field(..., description="Failed webhooks")
    avg_processing_time_ms: float = Field(..., description="Average processing time")
    worker_apps_total: int = Field(..., description="Registered worker apps")


class ErrorResponse(BaseModel):
    """Error response schema."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Error details")
    timestamp: datetime = Field(
        default_factory=now_utc, description="Error timestamp"
    )


# =============================================================================
# Authentication & Users
# =============================================================================


class Token(BaseModel):
    access_token: str
    token_type: str
    base_url: Optional[str] = None
    scopes: Optional[List[str]] = None


class TokenData(BaseModel):
    username: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    role: Optional[UserRole] = None

    model_config = ConfigDict(extra="ignore")


class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    role: UserRole = Field(default=UserRole.BASIC)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
