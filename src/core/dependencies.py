"""
FastAPI dependencies for dependency injection.

Provides easy integration between FastAPI's dependency system
and the application's DI container.
"""

from typing import Callable
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# from .container import get_container, Container
# from .models import db_helper
# from .interfaces.services import (
#     ITaskQueue,
#     IS3Service,
#     IDocumentProcessingService,
#     IDocumentContextService,
# )

# Import use cases


# Import repositories


# ============================================================================
# Repository Dependencies
# ============================================================================

# ============================================================================
# Use Case Dependencies
# ============================================================================


# Generic factory for creating dependency providers
def create_use_case_dependency(use_case_factory: Callable) -> Callable:
    """
    Generic factory for creating FastAPI dependency functions.

    Args:
        use_case_factory: Container factory method for the use case

    Returns:
        FastAPI dependency function

    Example:
        get_my_use_case = create_use_case_dependency(
            lambda container, session: container.my_use_case(session=session)
        )
    """

    def dependency(
        session: AsyncSession = Depends(db_helper.scoped_session_dependency),
        container: Container = Depends(get_container),
    ):
        return use_case_factory(container, session)

    return dependency


# ============================================================================
# Infrastructure Dependencies
# ============================================================================
