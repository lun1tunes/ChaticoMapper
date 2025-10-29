"""Repository for WorkerApp model."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.worker_app import WorkerApp
from src.core.repositories.base import BaseRepository


class WorkerAppRepository(BaseRepository[WorkerApp]):
    """Repository for worker app operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(WorkerApp, session)

    async def get_by_owner_id(self, owner_id: str) -> Optional[WorkerApp]:
        """
        Get worker app by Instagram owner ID.

        Args:
            owner_id: Instagram account ID

        Returns:
            WorkerApp if found, None otherwise
        """
        result = await self.session.execute(
            select(WorkerApp).where(WorkerApp.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_owner_id(self, owner_id: str) -> bool:
        """
        Check if worker app exists for owner ID.

        Args:
            owner_id: Instagram account ID

        Returns:
            True if exists, False otherwise
        """
        worker_app = await self.get_by_owner_id(owner_id)
        return worker_app is not None
