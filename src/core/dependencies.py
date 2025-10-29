"""
FastAPI dependencies for dependency injection.

Provides easy integration between FastAPI's dependency system
and the application's DI container.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.db_helper import db_helper


# ============================================================================
# Database Dependencies
# ============================================================================


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session.

    Yields:
        AsyncSession for database operations
    """
    async with db_helper.session_factory() as session:
        yield session
