"""Dependency injection container for Chatico Mapper App."""

from dependency_injector import containers, providers
from dependency_injector.wiring import Provide, inject
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings
from app.repositories import WebhookLogRepository, WorkerAppRepository
from app.services import (
    InstagramService,
    RabbitMQService,
    RoutingService,
    WebhookLoggingService,
)
from app.use_cases import (
    ManageWorkerAppsUseCase,
    ProcessWebhookUseCase,
    WebhookLoggingUseCase,
)


class Container(containers.DeclarativeContainer):
    """Dependency injection container."""

    # Configuration
    config = providers.Configuration()

    # Database
    database_engine = providers.Singleton(
        create_async_engine,
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.debug,
    )

    database_session_factory = providers.Singleton(
        async_sessionmaker,
        database_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    database_session = providers.Factory(
        lambda: database_session_factory()(),
    )

    # Repositories
    worker_app_repository = providers.Factory(
        WorkerAppRepository,
        session=database_session,
    )

    webhook_log_repository = providers.Factory(
        WebhookLogRepository,
        session=database_session,
    )

    # Services
    instagram_service = providers.Singleton(InstagramService)

    rabbitmq_service = providers.Singleton(RabbitMQService)

    routing_service = providers.Factory(
        RoutingService,
        worker_app_repository=worker_app_repository,
    )

    webhook_logging_service = providers.Factory(
        WebhookLoggingService,
        webhook_log_repository=webhook_log_repository,
    )

    # Use Cases
    process_webhook_use_case = providers.Factory(
        ProcessWebhookUseCase,
        instagram_service=instagram_service,
        rabbitmq_service=rabbitmq_service,
        routing_service=routing_service,
        webhook_logging_service=webhook_logging_service,
        worker_app_repository=worker_app_repository,
    )

    manage_worker_apps_use_case = providers.Factory(
        ManageWorkerAppsUseCase,
        worker_app_repository=worker_app_repository,
        rabbitmq_service=rabbitmq_service,
    )

    webhook_logging_use_case = providers.Factory(
        WebhookLoggingUseCase,
        webhook_log_repository=webhook_log_repository,
    )


# Global container instance
container = Container()
container.config.from_pydantic(settings)


# Dependency providers for FastAPI
def get_database_session() -> AsyncSession:
    """Get database session."""
    return container.database_session()


def get_process_webhook_use_case() -> ProcessWebhookUseCase:
    """Get process webhook use case."""
    return container.process_webhook_use_case()


def get_manage_worker_apps_use_case() -> ManageWorkerAppsUseCase:
    """Get manage worker apps use case."""
    return container.manage_worker_apps_use_case()


def get_webhook_logging_use_case() -> WebhookLoggingUseCase:
    """Get webhook logging use case."""
    return container.webhook_logging_use_case()


def get_instagram_service() -> InstagramService:
    """Get Instagram service."""
    return container.instagram_service()


def get_rabbitmq_service() -> RabbitMQService:
    """Get RabbitMQ service."""
    return container.rabbitmq_service()


def get_routing_service() -> RoutingService:
    """Get routing service."""
    return container.routing_service()
