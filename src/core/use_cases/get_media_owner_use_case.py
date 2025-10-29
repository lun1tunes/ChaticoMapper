"""Use case for getting media owner with caching strategy."""

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repositories.instagram_media_repository import InstagramMediaRepository
from src.core.services.instagram_api_service import InstagramAPIService
from src.core.services.redis_cache_service import RedisCacheService

logger = logging.getLogger(__name__)


class GetMediaOwnerUseCase:
    """
    Get owner_id for a media item using hybrid caching strategy.

    Lookup order:
    1. Redis cache (fast path - <1ms)
    2. PostgreSQL instagram_media table
    3. Instagram Graph API (slow path - ~100-200ms)
    """

    def __init__(
        self,
        session: AsyncSession,
        redis_cache: Optional[RedisCacheService],
        instagram_api: InstagramAPIService,
    ):
        self.session = session
        self.redis_cache = redis_cache
        self.instagram_api = instagram_api
        self.media_repo = InstagramMediaRepository(session)

    async def execute(self, media_id: str) -> dict:
        """
        Get owner information for a media item.

        Args:
            media_id: Instagram media ID

        Returns:
            dict with:
                - success (bool): Whether owner_id was retrieved
                - owner_id (str): Instagram account ID (if success=True)
                - owner_username (str): Instagram username (if available)
                - source (str): Where data came from (cache/database/api)
                - error (str): Error message (if success=False)
        """
        # Step 1: Check Redis cache (fast path)
        if self.redis_cache:
            cached_owner_id = await self.redis_cache.get_media_owner(media_id)
            if cached_owner_id:
                logger.debug("Media owner from cache: media_id=%s", media_id)
                return {
                    "success": True,
                    "owner_id": cached_owner_id,
                    "source": "cache",
                }

        # Step 2: Check database
        media = await self.media_repo.get_by_media_id(media_id)
        if media:
            logger.debug(f"Media owner from database: media_id={media_id}")

            # Cache for future lookups
            if self.redis_cache:
                await self.redis_cache.set_media_owner(media_id, media.owner_id)

            return {
                "success": True,
                "owner_id": media.owner_id,
                "owner_username": media.owner_username,
                "source": "database",
            }

        # Step 3: Fetch from Instagram API (slow path)
        logger.info(f"Fetching media owner from Instagram API: media_id={media_id}")
        api_result = await self.instagram_api.get_media_owner(media_id)

        if not api_result.get("success"):
            logger.error(
                f"Failed to fetch media owner: media_id={media_id}, "
                f"error={api_result.get('error')}"
            )
            return {
                "success": False,
                "error": api_result.get("error", "Instagram API error"),
                "status_code": api_result.get("status_code"),
                "source": "api",
            }

        owner_id = api_result.get("owner_id")
        owner_username = api_result.get("username")

        if not owner_id:
            logger.error(f"No owner_id in API response: media_id={media_id}")
            return {
                "success": False,
                "error": "No owner_id in API response",
                "source": "api",
            }

        # Store in database for future use
        try:
            await self.media_repo.create_or_update(
                media_id=media_id,
                owner_id=owner_id,
                owner_username=owner_username,
            )
            await self.session.commit()
            logger.info(f"Stored media in database: media_id={media_id}, owner_id={owner_id}")

        except Exception as e:
            logger.error(f"Failed to store media in database: {e}")
            # Don't fail the whole operation if DB write fails
            await self.session.rollback()

        # Cache in Redis
        if self.redis_cache:
            await self.redis_cache.set_media_owner(media_id, owner_id)

        return {
            "success": True,
            "owner_id": owner_id,
            "owner_username": owner_username,
            "source": "api",
        }
