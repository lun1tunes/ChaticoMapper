"""Repository for WorkerApp model."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.worker_app import WorkerApp
from src.core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


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

    async def get_active_by_owner_id(self, owner_id: str) -> Optional[WorkerApp]:
        """
        Get active worker app by owner ID.

        Args:
            owner_id: Instagram account ID

        Returns:
            Active WorkerApp if found, None otherwise
        """
        result = await self.session.execute(
            select(WorkerApp).where(
                WorkerApp.owner_id == owner_id,
                WorkerApp.is_active == True  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_all_active(self, limit: int = 100, offset: int = 0) -> list[WorkerApp]:
        """
        Get all active worker apps.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of active WorkerApp instances
        """
        result = await self.session.execute(
            select(WorkerApp)
            .where(WorkerApp.is_active == True)  # noqa: E712
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def toggle_active(self, worker_app_id: UUID) -> Optional[WorkerApp]:
        """
        Toggle is_active status of a worker app.

        Args:
            worker_app_id: Worker app UUID

        Returns:
            Updated WorkerApp if found, None otherwise
        """
        worker_app = await self.get_by_id(worker_app_id)
        if worker_app:
            worker_app.is_active = not worker_app.is_active
            await self.session.flush()
            logger.info(f"Toggled worker_app {worker_app_id} active status to {worker_app.is_active}")

        return worker_app

    async def get_by_queue_name(self, queue_name: str) -> Optional[WorkerApp]:
        """
        Get worker app by RabbitMQ queue name.

        Args:
            queue_name: RabbitMQ queue name

        Returns:
            WorkerApp if found, None otherwise
        """
        result = await self.session.execute(
            select(WorkerApp).where(WorkerApp.queue_name == queue_name)
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
