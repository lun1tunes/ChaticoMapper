"""
Dependency Injection Container.

Centralizes all dependency configuration following the Dependency Inversion Principle.
This makes the application more testable and maintainable.
"""

from dependency_injector import containers, providers
from redis import asyncio as redis_async

from .config import settings

# Services imports


# Infrastructure imports


# Use cases imports


# Repositories imports


class Container(containers.DeclarativeContainer):
    """
    Application DI container.

    Provides centralized configuration for all dependencies.
    Services are created as singletons or factories as appropriate.
    """

    # Configuration
    config = providers.Configuration()

    # Infrastructure - Singleton

    # Database infrastructure

    # Repository factories

    # Services - Factory (new instance each time, allows different configs)

    # Use Cases - Factory (new instance per request)
    # Note: session is provided at call time via Depends()


# Global container instance
container = Container()


def get_container() -> Container:
    """
    Get the global container instance.

    Used as a FastAPI dependency:
        container: Container = Depends(get_container)
    """
    return container


def reset_container():
    """
    Reset container for testing.

    Clears all singletons and allows fresh initialization.
    """
    container.reset_singletons()
