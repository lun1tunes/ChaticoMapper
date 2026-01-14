"""Repository for WorkerApp model."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.worker_app import WorkerApp
from src.core.repositories.base import BaseRepository


class WorkerAppRepository(BaseRepository[WorkerApp]):
    """Repository for worker app operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(WorkerApp, session)

    async def get_by_user_id(self, user_id: UUID) -> Optional[WorkerApp]:
        """
        Get worker app associated with a specific application user.

        Args:
            user_id: User ID

        Returns:
            WorkerApp if found, None otherwise
        """
        result = await self.session.execute(
            select(WorkerApp).where(WorkerApp.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_user_id(self, user_id: UUID) -> bool:
        """
        Check if worker app exists for user ID.

        Args:
            user_id: User ID

        Returns:
            True if exists, False otherwise
        """
        worker_app = await self.get_by_user_id(user_id)
        return worker_app is not None
