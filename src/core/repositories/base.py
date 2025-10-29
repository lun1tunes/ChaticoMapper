"""Base repository pattern for data access abstraction (Clean Architecture)."""

import logging
from typing import Generic, TypeVar, Type, Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import Base

T = TypeVar('T', bound=Base)
logger = logging.getLogger(__name__)


class BaseRepository(Generic[T]):
    """
    Generic repository for database operations.

    Provides common CRUD operations following Repository Pattern.
    Reduces duplication and provides clean data access layer.
    """

    def __init__(self, model: Type[T], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: str | int) -> Optional[T]:
        """Get entity by ID."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """Get all entities with pagination."""
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, entity: T) -> T:
        """Create new entity."""
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: T) -> T:
        """Update existing entity."""
        await self.session.flush()
        return entity

    async def delete(self, entity: T) -> None:
        """Delete entity."""
        await self.session.delete(entity)
        await self.session.flush()

    async def exists(self, id: str | int) -> bool:
        """Check if entity exists."""
        entity = await self.get_by_id(id)
        return entity is not None
