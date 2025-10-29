"""Pydantic schemas for Chatico Mapper App."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, ConfigDict


class InstagramWebhookEntry(BaseModel):
    """Instagram webhook entry schema."""

    id: str = Field(..., description="Entry ID")
    time: int = Field(..., description="Timestamp")
    changes: List[Dict[str, Any]] = Field(..., description="Change data")


class InstagramWebhookPayload(BaseModel):
    """Instagram webhook payload schema."""

    object: str = Field(..., description="Object type")
    entry: List[InstagramWebhookEntry] = Field(..., description="Webhook entries")


# Alias for backward compatibility
WebhookPayload = InstagramWebhookPayload


class InstagramComment(BaseModel):
    """Instagram comment schema."""

    id: str = Field(..., description="Comment ID")
    media_id: str = Field(..., description="Associated media ID")
    text: Optional[str] = Field(None, description="Comment text")
    from_user: Optional[Dict[str, Any]] = Field(None, description="Comment author")


class InstagramMedia(BaseModel):
    """Instagram media schema."""

    id: str = Field(..., description="Media ID")
    owner: Optional[Dict[str, Any]] = Field(None, description="Media owner information")
    media_type: Optional[str] = Field(None, description="Media type")
    media_url: Optional[str] = Field(None, description="Media URL")
    permalink: Optional[str] = Field(None, description="Media permalink")


class RoutingRequest(BaseModel):
    """Webhook routing request schema."""

    webhook_payload: InstagramWebhookPayload = Field(
        ..., description="Original webhook payload"
    )
    owner_id: str = Field(..., description="Instagram account ID")
    target_base_url: str = Field(..., description="Target worker app URL")
    target_owner_username: Optional[str] = Field(
        None, description="Instagram username of the target owner"
    )
    webhook_id: str = Field(..., description="Unique webhook ID")


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


class WorkerAppCreate(BaseModel):
    """Worker app creation schema."""

    owner_id: str = Field(
        ..., description="Instagram account ID", min_length=1, max_length=255
    )
    owner_instagram_username: str = Field(
        ..., description="Instagram username of the owner", min_length=1, max_length=255
    )
    base_url: HttpUrl = Field(..., description="Base URL for HTTP requests")


class WorkerAppUpdate(BaseModel):
    """Worker app update schema."""

    owner_instagram_username: Optional[str] = Field(
        None, description="Instagram username of the owner", min_length=1, max_length=255
    )
    base_url: Optional[HttpUrl] = Field(None, description="Base URL for HTTP requests")


class WorkerAppResponse(BaseModel):
    """Worker app response schema."""

    id: UUID = Field(..., description="Worker app ID")
    owner_id: str = Field(..., description="Instagram account ID")
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


class WebhookLogResponse(BaseModel):
    """Webhook log response schema."""

    id: UUID = Field(..., description="Log ID")
    webhook_id: str = Field(..., description="Unique webhook ID")
    owner_id: str = Field(..., description="Instagram account ID")
    worker_app_id: Optional[UUID] = Field(None, description="Target worker app ID")
    target_owner_username: Optional[str] = Field(
        None, description="Target Instagram username"
    )
    target_base_url: Optional[str] = Field(None, description="Target base URL")
    status: str = Field(..., description="Processing status")
    error_message: Optional[str] = Field(None, description="Error messages")
    processing_time_ms: Optional[int] = Field(
        None, description="Processing time in milliseconds"
    )
    created_at: datetime = Field(..., description="Created timestamp")

    model_config = ConfigDict(from_attributes=True)


class WebhookLogListResponse(BaseModel):
    """Webhook log list response schema."""

    items: List[WebhookLogResponse] = Field(..., description="List of webhook logs")
    total: int = Field(..., description="Total count")
    page: int = Field(..., description="Current page")
    size: int = Field(..., description="Page size")


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(..., description="Check timestamp")
    version: str = Field(..., description="Application version")
    services: Dict[str, str] = Field(..., description="Service statuses")


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
        default_factory=datetime.utcnow, description="Error timestamp"
    )
