"""
FastAPI dependencies for dependency injection.

Provides easy integration between FastAPI's dependency system
and the application's DI container.
"""

from typing import Annotated, AsyncGenerator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.models.db_helper import db_helper
from src.core.models.user import User
from src.core.repositories.user_repository import UserRepository
from src.core.repositories.worker_app_repository import WorkerAppRepository
from src.core.repositories.instagram_media_repository import InstagramMediaRepository
from src.core.repositories.instagram_comment_repository import InstagramCommentRepository
from src.core.repositories.webhook_log_repository import WebhookLogRepository
from src.core.services.redis_cache_service import RedisCacheService
from src.core.services.instagram_api_service import InstagramAPIService
from src.core.services.security import TokenDecodeError, safe_decode_token
from src.core.use_cases.get_media_owner_use_case import GetMediaOwnerUseCase
from src.core.use_cases.forward_webhook_use_case import ForwardWebhookUseCase
from src.core.use_cases.process_webhook_use_case import ProcessWebhookUseCase
from src.api_v1.schemas import TokenData


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


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)]
) -> UserRepository:
    """Get UserRepository instance."""
    return UserRepository(session)


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


# ============================================================================
# Authentication Dependencies
# ============================================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    scopes={
        "me": "Read information about the current user.",
        "items": "Read items that belong to the current user.",
    },
)


async def get_current_user(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(oauth2_scheme)],
    repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> User:
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )

    try:
        payload = safe_decode_token(token)
    except TokenDecodeError:
        raise credentials_exception

    token_data = TokenData(
        username=payload.get("sub"),
        scopes=payload.get("scopes", []),
    )
    if not token_data.username:
        raise credentials_exception

    for scope in security_scopes.scopes:
        if scope not in token_data.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
                headers={"WWW-Authenticate": authenticate_value},
            )

    user = await repo.get_by_email(token_data.username)
    if not user:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user
