"""Repository for WebhookLog model."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.webhook_log import WebhookLog
from src.core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class WebhookLogRepository(BaseRepository[WebhookLog]):
    """Repository for webhook log operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(WebhookLog, session)

    async def get_by_webhook_id(self, webhook_id: str) -> Optional[WebhookLog]:
        """
        Get log entry by webhook ID.

        Args:
            webhook_id: Unique webhook identifier

        Returns:
            WebhookLog if found, None otherwise
        """
        result = await self.session.execute(
            select(WebhookLog).where(WebhookLog.webhook_id == webhook_id)
        )
        return result.scalar_one_or_none()

    async def get_by_owner_id(
        self,
        owner_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> list[WebhookLog]:
        """
        Get all logs for an owner.

        Args:
            owner_id: Instagram account ID
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of WebhookLog instances
        """
        result = await self.session.execute(
            select(WebhookLog)
            .where(WebhookLog.owner_id == owner_id)
            .order_by(WebhookLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_worker_app_id(
        self,
        worker_app_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> list[WebhookLog]:
        """
        Get all logs for a worker app.

        Args:
            worker_app_id: Worker app UUID
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of WebhookLog instances
        """
        result = await self.session.execute(
            select(WebhookLog)
            .where(WebhookLog.worker_app_id == worker_app_id)
            .order_by(WebhookLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_by_status(
        self,
        status: str,
        limit: int = 100,
        offset: int = 0
    ) -> list[WebhookLog]:
        """
        Get logs by processing status.

        Args:
            status: Processing status (success, failed, routed, etc.)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of WebhookLog instances
        """
        result = await self.session.execute(
            select(WebhookLog)
            .where(WebhookLog.status == status)
            .order_by(WebhookLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_status(self, status: str) -> int:
        """
        Count logs by processing status.

        Args:
            status: Processing status

        Returns:
            Count of logs
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(WebhookLog)
            .where(WebhookLog.status == status)
        )
        return result.scalar_one()

    async def count_by_owner_id(self, owner_id: str) -> int:
        """
        Count logs for an owner.

        Args:
            owner_id: Instagram account ID

        Returns:
            Count of logs
        """
        result = await self.session.execute(
            select(func.count()).select_from(WebhookLog).where(
                WebhookLog.owner_id == owner_id
            )
        )
        return result.scalar_one()

    async def get_failed_logs(self, limit: int = 100, offset: int = 0) -> list[WebhookLog]:
        """
        Get all failed webhook logs.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of failed WebhookLog instances
        """
        return await self.get_by_status("failed", limit, offset)

    async def exists_by_webhook_id(self, webhook_id: str) -> bool:
        """
        Check if log exists by webhook ID.

        Args:
            webhook_id: Unique webhook identifier

        Returns:
            True if exists, False otherwise
        """
        log = await self.get_by_webhook_id(webhook_id)
        return log is not None
