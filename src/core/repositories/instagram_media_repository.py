"""Repository for InstagramMedia model."""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.instagram_media import InstagramMedia
from src.core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class InstagramMediaRepository(BaseRepository[InstagramMedia]):
    """Repository for Instagram media operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(InstagramMedia, session)

    async def get_by_media_id(self, media_id: str) -> Optional[InstagramMedia]:
        """
        Get media by Instagram media ID.

        Args:
            media_id: Instagram media ID

        Returns:
            InstagramMedia if found, None otherwise
        """
        result = await self.session.execute(
            select(InstagramMedia).where(InstagramMedia.media_id == media_id)
        )
        return result.scalar_one_or_none()

    async def get_by_owner_id(
        self,
        owner_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> list[InstagramMedia]:
        """
        Get all media for an owner.

        Args:
            owner_id: Instagram account ID
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of InstagramMedia instances
        """
        result = await self.session.execute(
            select(InstagramMedia)
            .where(InstagramMedia.owner_id == owner_id)
            .order_by(InstagramMedia.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def exists_by_media_id(self, media_id: str) -> bool:
        """
        Check if media exists by media ID.

        Args:
            media_id: Instagram media ID

        Returns:
            True if exists, False otherwise
        """
        media = await self.get_by_media_id(media_id)
        return media is not None

    async def get_owner_id(self, media_id: str) -> Optional[str]:
        """
        Get just the owner_id for a media (lightweight query).

        Args:
            media_id: Instagram media ID

        Returns:
            owner_id if found, None otherwise
        """
        result = await self.session.execute(
            select(InstagramMedia.owner_id).where(InstagramMedia.media_id == media_id)
        )
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        media_id: str,
        owner_id: str,
        owner_username: Optional[str] = None,
        permalink: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> InstagramMedia:
        """
        Create new media or update existing.

        Args:
            media_id: Instagram media ID
            owner_id: Instagram account ID
            owner_username: Instagram username
            permalink: Media permalink URL
            media_type: Media type (IMAGE, VIDEO, CAROUSEL_ALBUM)

        Returns:
            InstagramMedia instance
        """
        existing = await self.get_by_media_id(media_id)

        if existing:
            # Update existing
            existing.owner_id = owner_id
            if owner_username:
                existing.owner_username = owner_username
            if permalink:
                existing.permalink = permalink
            if media_type:
                existing.media_type = media_type

            await self.session.flush()
            logger.debug(f"Updated media: media_id={media_id}")
            return existing

        else:
            # Create new
            media = InstagramMedia(
                media_id=media_id,
                owner_id=owner_id,
                owner_username=owner_username,
                permalink=permalink,
                media_type=media_type,
            )
            self.session.add(media)
            await self.session.flush()
            logger.debug(f"Created media: media_id={media_id}, owner_id={owner_id}")
            return media
