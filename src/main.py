"""Main FastAPI application for Chatico Mapper App."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.api_v1 import webhook, worker_apps
from src.core.config import get_settings
from src.core.logging_config import setup_logging
from src.core.middleware.webhook_verification import WebhookVerificationMiddleware
from src.core.models.db_helper import db_helper

# Configure logging based on environment settings early during startup
settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events for the application.
    """
    # Startup
    logger.info("Starting Chatico Mapper App...")
    settings = get_settings()

    # Initialize database
    try:
        # Test database connection
        async with db_helper.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

    logger.info(f"Chatico Mapper App started successfully on {settings.host}:{settings.port}")

    yield

    # Shutdown
    logger.info("Shutting down Chatico Mapper App...")

    # Close database connections
    await db_helper.dispose()
    logger.info("Database connections closed")

    logger.info("Chatico Mapper App shut down complete")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Instagram webhook mapper for routing comments to worker applications",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # ========================================
    # Middleware
    # ========================================

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Webhook verification middleware
    # This verifies Instagram webhook signatures using HMAC-SHA256
    app.add_middleware(
        WebhookVerificationMiddleware,
        app_secret=settings.webhook.secret,
        verify_webhook_paths=["/webhook", "/webhook/"],
        development_mode=settings.debug,
    )

    # ========================================
    # Routers
    # ========================================

    # Include API routers
    app.include_router(webhook.router, prefix="/api/v1")
    app.include_router(worker_apps.router, prefix="/api/v1")

    # ========================================
    # Root Endpoints
    # ========================================

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "status": "running",
            "docs": "/docs",
        }

    @app.get("/health")
    async def health():
        """
        Health check endpoint.

        Returns:
            Health status of the application and its dependencies
        """
        try:
            # Check database connection
            async with db_helper.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "healthy"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            db_status = "unhealthy"

        overall_status = "healthy" if db_status == "healthy" else "degraded"

        return {
            "status": overall_status,
            "services": {
                "database": db_status,
            },
        }

    # ========================================
    # Exception Handlers
    # ========================================

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        """Global exception handler for unhandled errors."""
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "type": "internal_error",
            },
        )

    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    """
    Run the application using uvicorn.

    For development: python src/main.py
    For production: use uvicorn directly or fastapi run command
    """
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
