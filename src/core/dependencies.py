"""
FastAPI dependencies for dependency injection.

Provides easy integration between FastAPI's dependency system
and the application's DI container.
"""

from typing import Annotated, AsyncGenerator, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.models.db_helper import db_helper
from src.core.repositories.worker_app_repository import WorkerAppRepository
from src.core.repositories.instagram_media_repository import InstagramMediaRepository
from src.core.repositories.instagram_comment_repository import InstagramCommentRepository
from src.core.repositories.webhook_log_repository import WebhookLogRepository
from src.core.services.redis_cache_service import RedisCacheService
from src.core.services.instagram_api_service import InstagramAPIService
from src.core.use_cases.get_media_owner_use_case import GetMediaOwnerUseCase
from src.core.use_cases.forward_webhook_use_case import ForwardWebhookUseCase
from src.core.use_cases.process_webhook_use_case import ProcessWebhookUseCase


# ============================================================================
# Database Dependencies
# ============================================================================


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session.

    Yields:
        AsyncSession for database operations
    """
    async with db_helper.session_factory() as session:
        yield session


# ============================================================================
# Repository Dependencies
# ============================================================================


def get_worker_app_repository(
    session: Annotated[AsyncSession, Depends(get_session)]
) -> WorkerAppRepository:
    """Get WorkerAppRepository instance."""
    return WorkerAppRepository(session)


def get_instagram_media_repository(
    session: Annotated[AsyncSession, Depends(get_session)]
) -> InstagramMediaRepository:
    """Get InstagramMediaRepository instance."""
    return InstagramMediaRepository(session)


def get_instagram_comment_repository(
    session: Annotated[AsyncSession, Depends(get_session)]
) -> InstagramCommentRepository:
    """Get InstagramCommentRepository instance."""
    return InstagramCommentRepository(session)


def get_webhook_log_repository(
    session: Annotated[AsyncSession, Depends(get_session)]
) -> WebhookLogRepository:
    """Get WebhookLogRepository instance."""
    return WebhookLogRepository(session)


# ============================================================================
# Service Dependencies
# ============================================================================


async def get_redis_cache_service(
    settings: Annotated[Settings, Depends(get_settings)]
) -> AsyncGenerator[Optional[RedisCacheService], None]:
    """
    Get RedisCacheService instance with connection management.

    Yields:
        Connected RedisCacheService instance
    """
    redis_url = settings.redis.url

    if not redis_url:
        # Redis is optional; yield None so downstream dependencies can fall back.
        yield None
        return

    service = RedisCacheService(
        redis_url=redis_url,
        default_ttl=settings.redis.ttl,
    )
    await service.connect()
    try:
        yield service
    finally:
        await service.disconnect()


async def get_instagram_api_service(
    settings: Annotated[Settings, Depends(get_settings)]
) -> AsyncGenerator[InstagramAPIService, None]:
    """
    Get InstagramAPIService instance with connection management.

    Yields:
        InstagramAPIService instance
    """
    service = InstagramAPIService(
        access_token=settings.instagram.access_token,
        api_base_url=settings.instagram.api_base_url,
        timeout=settings.instagram.api_timeout,
    )
    try:
        yield service
    finally:
        await service.close()


# ============================================================================
# Use Case Dependencies
# ============================================================================


def get_media_owner_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_cache: Annotated[Optional[RedisCacheService], Depends(get_redis_cache_service)],
    instagram_api: Annotated[InstagramAPIService, Depends(get_instagram_api_service)],
) -> GetMediaOwnerUseCase:
    """Get GetMediaOwnerUseCase instance with all dependencies."""
    return GetMediaOwnerUseCase(
        session=session,
        redis_cache=redis_cache,
        instagram_api=instagram_api,
    )


def get_forward_webhook_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ForwardWebhookUseCase:
    """Get ForwardWebhookUseCase instance."""
    return ForwardWebhookUseCase(
        session=session,
        http_timeout=30.0,
    )


def get_process_webhook_use_case(
    session: Annotated[AsyncSession, Depends(get_session)],
    get_media_owner_uc: Annotated[GetMediaOwnerUseCase, Depends(get_media_owner_use_case)],
    forward_webhook_uc: Annotated[ForwardWebhookUseCase, Depends(get_forward_webhook_use_case)],
    redis_cache: Annotated[Optional[RedisCacheService], Depends(get_redis_cache_service)],
) -> ProcessWebhookUseCase:
    """Get ProcessWebhookUseCase instance with all dependencies."""
    return ProcessWebhookUseCase(
        session=session,
        get_media_owner_uc=get_media_owner_uc,
        forward_webhook_uc=forward_webhook_uc,
        redis_cache=redis_cache,
    )
