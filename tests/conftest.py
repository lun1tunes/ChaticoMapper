"""Pytest configuration and shared fixtures for Chatico Mapper App tests."""

import asyncio
import os
import tempfile
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient
from fastapi import FastAPI

# Set test environment variables before importing app modules
os.environ.update(
    {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "RABBITMQ_URL": "amqp://guest:guest@localhost:5672/",
        "REDIS_URL": "redis://localhost:6379/0",
        "INSTAGRAM_APP_ID": "test_app_id",
        "INSTAGRAM_APP_SECRET": "test_app_secret",
        "INSTAGRAM_ACCESS_TOKEN": "test_access_token",
        "WEBHOOK_SECRET": "test_webhook_secret",
        "WEBHOOK_VERIFY_TOKEN": "test_verify_token",
        "SECRET_KEY": "test_secret_key",
        "DEBUG": "true",
        "LOG_LEVEL": "DEBUG",
    }
)

from app.main import app
from app.models import Base
from app.dependencies import Container
from app.config import Settings


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create a test database engine."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        app_name="Chatico Mapper App Test",
        app_version="0.1.0-test",
        debug=True,
        log_level="DEBUG",
        database_url="sqlite+aiosqlite:///:memory:",
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        redis_url="redis://localhost:6379/0",
        instagram_app_id="test_app_id",
        instagram_app_secret="test_app_secret",
        instagram_access_token="test_access_token",
        webhook_secret="test_webhook_secret",
        webhook_verify_token="test_verify_token",
        secret_key="test_secret_key",
    )


@pytest.fixture
def container(test_settings: Settings) -> Container:
    """Create a test dependency injection container."""
    container = Container()
    container.config.from_dict(
        {
            "settings": test_settings,
        }
    )
    return container


@pytest_asyncio.fixture
async def test_app(db_session: AsyncSession) -> FastAPI:
    """Create a test FastAPI application."""
    # Override the database session dependency
    app.dependency_overrides[Container.database_session] = lambda: db_session
    return app


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create a test HTTP client."""
    async with AsyncClient(app=test_app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_instagram_service():
    """Create a mock Instagram service."""
    mock = AsyncMock()
    mock.get_media_info.return_value = {
        "id": "test_media_id",
        "owner": {"id": "test_owner_id"},
        "media_type": "IMAGE",
        "media_url": "https://example.com/image.jpg",
        "timestamp": "2024-01-01T00:00:00Z",
    }
    mock.extract_owner_id.return_value = "test_owner_id"
    return mock


@pytest.fixture
def mock_rabbitmq_service():
    """Create a mock RabbitMQ service."""
    mock = AsyncMock()
    mock.publish_message.return_value = True
    mock.create_queue.return_value = True
    mock.get_queue_info.return_value = {
        "message_count": 0,
        "consumer_count": 0,
        "state": "running",
    }
    return mock


@pytest.fixture
def mock_routing_service():
    """Create a mock routing service."""
    mock = AsyncMock()
    mock.find_worker_app_by_owner_id.return_value = {
        "id": "test_worker_app_id",
        "owner_id": "test_owner_id",
        "app_name": "Test Worker App",
        "base_url": "https://test-worker.example.com",
        "webhook_path": "/webhook",
        "queue_name": "test_queue",
        "is_active": True,
    }
    mock.is_worker_app_healthy.return_value = True
    return mock


@pytest.fixture
def mock_webhook_logging_service():
    """Create a mock webhook logging service."""
    mock = AsyncMock()
    mock.log_webhook_processing.return_value = None
    mock.get_webhook_stats.return_value = {
        "total": 100,
        "success": 95,
        "failed": 5,
        "routed": 90,
    }
    return mock


@pytest.fixture
def sample_webhook_payload():
    """Create a sample Instagram webhook payload."""
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "test_entry_id",
                "time": 1640995200,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "test_comment_id",
                            "text": "Test comment",
                            "media_id": "test_media_id",
                            "from": {
                                "id": "test_user_id",
                                "username": "test_user",
                            },
                            "created_time": "2024-01-01T00:00:00Z",
                        },
                    }
                ],
            }
        ],
    }


@pytest.fixture
def sample_worker_app_data():
    """Create sample worker app data."""
    return {
        "owner_id": "test_owner_id",
        "app_name": "Test Worker App",
        "base_url": "https://test-worker.example.com",
        "webhook_path": "/webhook",
        "queue_name": "test_queue",
        "is_active": True,
    }


@pytest.fixture
def sample_routing_request():
    """Create a sample routing request."""
    return {
        "webhook_payload": {
            "object": "instagram",
            "entry": [
                {
                    "id": "test_entry_id",
                    "time": 1640995200,
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": "test_comment_id",
                                "text": "Test comment",
                                "media_id": "test_media_id",
                                "from": {
                                    "id": "test_user_id",
                                    "username": "test_user",
                                },
                                "created_time": "2024-01-01T00:00:00Z",
                            },
                        }
                    ],
                }
            ],
        },
        "owner_id": "test_owner_id",
        "target_app_url": "https://test-worker.example.com/webhook",
        "target_queue_name": "test_queue",
    }


@pytest.fixture
def sample_routing_response():
    """Create a sample routing response."""
    return {
        "status": "success",
        "message": "Webhook routed successfully",
        "routed_to": "test_queue",
        "processing_time_ms": 150,
        "error_details": None,
    }


@pytest.fixture
def mock_httpx_client():
    """Create a mock HTTPX client for external API calls."""
    mock = AsyncMock()
    mock.get.return_value.status_code = 200
    mock.get.return_value.json.return_value = {
        "id": "test_media_id",
        "owner": {"id": "test_owner_id"},
        "media_type": "IMAGE",
        "media_url": "https://example.com/image.jpg",
        "timestamp": "2024-01-01T00:00:00Z",
    }
    mock.post.return_value.status_code = 200
    mock.post.return_value.json.return_value = {"success": True}
    return mock


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    mock = AsyncMock()
    mock.get.return_value = None
    mock.set.return_value = True
    mock.delete.return_value = True
    mock.exists.return_value = False
    return mock


@pytest.fixture
def mock_aio_pika_connection():
    """Create a mock aio-pika connection."""
    mock_connection = AsyncMock()
    mock_channel = AsyncMock()
    mock_queue = AsyncMock()
    mock_exchange = AsyncMock()

    mock_connection.channel.return_value = mock_channel
    mock_channel.declare_queue.return_value = mock_queue
    mock_channel.declare_exchange.return_value = mock_exchange
    mock_queue.bind.return_value = None

    return mock_connection


@pytest.fixture
def temp_file():
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test content")
        temp_path = f.name

    yield temp_path

    # Cleanup
    try:
        os.unlink(temp_path)
    except OSError:
        pass


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line(
        "markers", "external: mark test as requiring external services"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers."""
    for item in items:
        # Add unit marker to tests in unit directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Add integration marker to tests in integration directory
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Add slow marker to tests with "slow" in the name
        if "slow" in item.name:
            item.add_marker(pytest.mark.slow)

        # Add external marker to tests with "external" in the name
        if "external" in item.name:
            item.add_marker(pytest.mark.external)
