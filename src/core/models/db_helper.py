"""Database helper for async SQLAlchemy session management."""

import inspect
from asyncio import current_task

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings


class DatabaseHelper:
    """Helper for managing database connections and sessions."""

    def __init__(self, url: str, echo: bool = False, pool_size: int = 20, max_overflow: int = 30):
        """
        Initialize database helper.

        Args:
            url: Database connection URL
            echo: Echo SQL queries
            pool_size: Connection pool size
            max_overflow: Max overflow connections
        """
        self.engine: AsyncEngine = create_async_engine(
            url=url,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    async def dispose(self) -> None:
        """Dispose of the engine and close all connections."""
        await self.engine.dispose()

    async def session_dependency(self) -> AsyncSession:  # type: ignore
        """FastAPI dependency for database sessions."""
        async with self.session_factory() as session:
            yield session

    async def scoped_session_dependency(self) -> AsyncSession:  # type: ignore
        """FastAPI dependency for scoped database sessions."""
        scoped_session = self.get_scoped_session()
        session = scoped_session()
        try:
            yield session
        finally:
            await session.close()
            remove_result = scoped_session.remove()
            if inspect.isawaitable(remove_result):
                await remove_result

    def get_scoped_session(self):
        """Get scoped session bound to current async task."""
        return async_scoped_session(
            session_factory=self.session_factory,
            scopefunc=current_task,
        )


# Global database helper instance
settings = get_settings()
db_helper = DatabaseHelper(
    url=settings.database_url,
    echo=settings.debug,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)
