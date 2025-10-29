"""Repository pattern implementations for Chatico Mapper App."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import WebhookLog, WorkerApp


class BaseRepository:
    """Base repository class with common functionality."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        self.session = session


class WorkerAppRepository(BaseRepository):
    """Repository for WorkerApp model operations."""

    async def create(self, worker_app: WorkerApp) -> WorkerApp:
        """Create a new worker app."""
        self.session.add(worker_app)
        await self.session.commit()
        await self.session.refresh(worker_app)
        return worker_app

    async def get_by_id(self, app_id: UUID) -> Optional[WorkerApp]:
        """Get worker app by ID."""
        result = await self.session.execute(
            select(WorkerApp).where(WorkerApp.id == app_id)
        )
        return result.scalar_one_or_none()

    async def get_by_owner_id(self, owner_id: str) -> Optional[WorkerApp]:
        """Get worker app by owner ID."""
        result = await self.session.execute(
            select(WorkerApp).where(
                and_(WorkerApp.owner_id == owner_id, WorkerApp.is_active == True)
            )
        )
        return result.scalar_one_or_none()

    async def get_all(
        self, skip: int = 0, limit: int = 100, active_only: bool = False
    ) -> List[WorkerApp]:
        """Get all worker apps with pagination."""
        query = select(WorkerApp)

        if active_only:
            query = query.where(WorkerApp.is_active == True)

        query = query.order_by(desc(WorkerApp.created_at)).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def count(self, active_only: bool = False) -> int:
        """Count total worker apps."""
        query = select(func.count(WorkerApp.id))

        if active_only:
            query = query.where(WorkerApp.is_active == True)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def update(self, app_id: UUID, **kwargs) -> Optional[WorkerApp]:
        """Update worker app by ID."""
        worker_app = await self.get_by_id(app_id)
        if not worker_app:
            return None

        for key, value in kwargs.items():
            if hasattr(worker_app, key):
                setattr(worker_app, key, value)

        await self.session.commit()
        await self.session.refresh(worker_app)
        return worker_app

    async def delete(self, app_id: UUID) -> bool:
        """Delete worker app by ID."""
        worker_app = await self.get_by_id(app_id)
        if not worker_app:
            return False

        await self.session.delete(worker_app)
        await self.session.commit()
        return True

    async def get_active_apps(self) -> List[WorkerApp]:
        """Get all active worker apps."""
        result = await self.session.execute(
            select(WorkerApp)
            .where(WorkerApp.is_active == True)
            .order_by(WorkerApp.app_name)
        )
        return result.scalars().all()

    async def exists_by_owner_id(self, owner_id: str) -> bool:
        """Check if worker app exists by owner ID."""
        result = await self.session.execute(
            select(func.count(WorkerApp.id)).where(WorkerApp.owner_id == owner_id)
        )
        return (result.scalar() or 0) > 0

    async def exists_by_queue_name(self, queue_name: str) -> bool:
        """Check if worker app exists by queue name."""
        result = await self.session.execute(
            select(func.count(WorkerApp.id)).where(WorkerApp.queue_name == queue_name)
        )
        return (result.scalar() or 0) > 0


class WebhookLogRepository(BaseRepository):
    """Repository for WebhookLog model operations."""

    async def create(self, webhook_log: WebhookLog) -> WebhookLog:
        """Create a new webhook log."""
        self.session.add(webhook_log)
        await self.session.commit()
        await self.session.refresh(webhook_log)
        return webhook_log

    async def get_by_id(self, log_id: UUID) -> Optional[WebhookLog]:
        """Get webhook log by ID."""
        result = await self.session.execute(
            select(WebhookLog)
            .options(selectinload(WebhookLog.worker_app))
            .where(WebhookLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def get_by_webhook_id(self, webhook_id: str) -> Optional[WebhookLog]:
        """Get webhook log by webhook ID."""
        result = await self.session.execute(
            select(WebhookLog)
            .options(selectinload(WebhookLog.worker_app))
            .where(WebhookLog.webhook_id == webhook_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        owner_id: Optional[str] = None,
        status: Optional[str] = None,
        worker_app_id: Optional[UUID] = None,
    ) -> List[WebhookLog]:
        """Get all webhook logs with filtering and pagination."""
        query = select(WebhookLog).options(selectinload(WebhookLog.worker_app))

        if owner_id:
            query = query.where(WebhookLog.owner_id == owner_id)

        if status:
            query = query.where(WebhookLog.processing_status == status)

        if worker_app_id:
            query = query.where(WebhookLog.worker_app_id == worker_app_id)

        query = query.order_by(desc(WebhookLog.created_at)).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def count(
        self,
        owner_id: Optional[str] = None,
        status: Optional[str] = None,
        worker_app_id: Optional[UUID] = None,
    ) -> int:
        """Count webhook logs with filtering."""
        query = select(func.count(WebhookLog.id))

        if owner_id:
            query = query.where(WebhookLog.owner_id == owner_id)

        if status:
            query = query.where(WebhookLog.processing_status == status)

        if worker_app_id:
            query = query.where(WebhookLog.worker_app_id == worker_app_id)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_stats_by_owner_id(self, owner_id: str) -> dict:
        """Get webhook processing statistics by owner ID."""
        result = await self.session.execute(
            select(
                WebhookLog.processing_status,
                func.count(WebhookLog.id).label("count"),
                func.avg(WebhookLog.processing_time_ms).label("avg_time"),
            )
            .where(WebhookLog.owner_id == owner_id)
            .group_by(WebhookLog.processing_status)
        )

        stats = {}
        for row in result:
            stats[row.processing_status] = {
                "count": row.count,
                "avg_time_ms": float(row.avg_time) if row.avg_time else None,
            }

        return stats

    async def get_stats_by_worker_app(self, worker_app_id: UUID) -> dict:
        """Get webhook processing statistics by worker app."""
        result = await self.session.execute(
            select(
                WebhookLog.processing_status,
                func.count(WebhookLog.id).label("count"),
                func.avg(WebhookLog.processing_time_ms).label("avg_time"),
            )
            .where(WebhookLog.worker_app_id == worker_app_id)
            .group_by(WebhookLog.processing_status)
        )

        stats = {}
        for row in result:
            stats[row.processing_status] = {
                "count": row.count,
                "avg_time_ms": float(row.avg_time) if row.avg_time else None,
            }

        return stats

    async def get_recent_logs(
        self, hours: int = 24, limit: int = 100
    ) -> List[WebhookLog]:
        """Get recent webhook logs within specified hours."""
        from datetime import datetime, timedelta

        since = datetime.utcnow() - timedelta(hours=hours)

        result = await self.session.execute(
            select(WebhookLog)
            .options(selectinload(WebhookLog.worker_app))
            .where(WebhookLog.created_at >= since)
            .order_by(desc(WebhookLog.created_at))
            .limit(limit)
        )

        return result.scalars().all()

    async def get_failed_logs(
        self, skip: int = 0, limit: int = 100
    ) -> List[WebhookLog]:
        """Get failed webhook logs."""
        result = await self.session.execute(
            select(WebhookLog)
            .options(selectinload(WebhookLog.worker_app))
            .where(WebhookLog.processing_status == "failed")
            .order_by(desc(WebhookLog.created_at))
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def cleanup_old_logs(self, days: int = 30) -> int:
        """Clean up webhook logs older than specified days."""
        from datetime import datetime, timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        result = await self.session.execute(
            select(func.count(WebhookLog.id)).where(WebhookLog.created_at < cutoff_date)
        )

        count = result.scalar() or 0

        if count > 0:
            await self.session.execute(
                select(WebhookLog).where(WebhookLog.created_at < cutoff_date)
            )
            await self.session.commit()

        return count
