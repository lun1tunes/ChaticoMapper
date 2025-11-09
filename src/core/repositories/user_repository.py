"""Repository for User model."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.user import User
from src.core.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository providing CRUD operations for users."""

    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
