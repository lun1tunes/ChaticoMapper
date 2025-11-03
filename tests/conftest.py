"""
Pytest configuration and helpers for the Chatico Mapper App test-suite.

The application expects environment settings and a PostgreSQL database, so the
fixtures below provide an isolated in-memory SQLite database and override the
FastAPI dependencies accordingly. We also stub the Instagram client and skip
lifespan start-up checks to keep tests fast and deterministic.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Environment bootstrap
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DB_URL = "sqlite+aiosqlite:///:memory:?cache=shared"

os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["JWT_SECRET_KEY"] = "test_secret_key"
os.environ["INSTAGRAM_APP_SECRET"] = "test_app_secret"
os.environ["INSTAGRAM_API_BASE_URL"] = "https://graph.instagram.com/v23.0"
os.environ["WEBHOOK_INIT_VERIFY_TOKEN"] = "test_verify_token"
os.environ["HOST"] = "0.0.0.0"
os.environ["PORT"] = "8100"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["REDIS_URL"] = ""
os.environ["REDIS_TTL"] = "86400"

from src.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from src.core.dependencies import get_redis_cache_service, get_session  # noqa: E402
from src.core.models import (
    instagram_comment,
    webhook_log,
    worker_app,
)  # noqa: E402,F401
from src.core.models.base import Base  # noqa: E402
from src.core.models.db_helper import db_helper  # noqa: E402
from src.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def prepare_database() -> AsyncGenerator[None, None]:
    """Initialise the in-memory SQLite schema for tests."""
    async def _setup() -> None:
        async with db_helper.engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_setup())

    yield

    asyncio.run(db_helper.dispose())


@pytest_asyncio.fixture
async def db_session(prepare_database: None) -> AsyncGenerator[AsyncSession, None]:
    async with db_helper.session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


# ---------------------------------------------------------------------------
# Dependency overrides
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def override_dependencies() -> Generator[None, None, None]:
    """Override FastAPI dependencies so the app uses the test resources."""

    async def _get_session_override() -> AsyncGenerator[AsyncSession, None]:
        async with db_helper.session_factory() as session:
            yield session

    async def _get_redis_override() -> AsyncGenerator[None, None]:
        yield None

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_redis_cache_service] = _get_redis_override

    try:
        yield
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTPX client configured for the ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
