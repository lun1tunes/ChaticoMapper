"""Repository for InstagramComment model."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.instagram_comment import InstagramComment
from src.core.repositories.base import BaseRepository


class InstagramCommentRepository(BaseRepository[InstagramComment]):
    """Repository for Instagram comment operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(InstagramComment, session)

    async def get_by_comment_id(self, comment_id: str) -> Optional[InstagramComment]:
        """
        Get comment by Instagram comment ID.

        Args:
            comment_id: Instagram comment ID

        Returns:
            InstagramComment if found, None otherwise
        """
        result = await self.session.execute(
            select(InstagramComment).where(InstagramComment.comment_id == comment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> list[InstagramComment]:
        """
        Get all comments by a user.

        Args:
            user_id: Instagram user ID
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of InstagramComment instances
        """
        result = await self.session.execute(
            select(InstagramComment)
            .where(InstagramComment.user_id == user_id)
            .order_by(InstagramComment.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_replies(self, parent_comment_id: str) -> list[InstagramComment]:
        """
        Get all replies to a comment.

        Args:
            parent_comment_id: Parent comment ID

        Returns:
            List of reply InstagramComment instances
        """
        result = await self.session.execute(
            select(InstagramComment)
            .where(InstagramComment.parent_id == parent_comment_id)
            .order_by(InstagramComment.created_at.asc())
        )
        return list(result.scalars().all())

    async def exists_by_comment_id(self, comment_id: str) -> bool:
        """
        Check if comment exists by comment ID.

        Args:
            comment_id: Instagram comment ID

        Returns:
            True if exists, False otherwise
        """
        comment = await self.get_by_comment_id(comment_id)
        return comment is not None
