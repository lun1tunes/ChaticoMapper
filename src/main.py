"""Main FastAPI application for Chatico Mapper App."""

import hashlib
import hmac
import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.api_v1.auth import router as auth_router
from src.api_v1.google_oauth import router as google_oauth_router
from src.api_v1.instagram_oauth import router as instagram_oauth_router
from src.api_v1.users import router as users_router
from src.api_v1.webhook import router as webhook_router
from src.api_v1.worker_apps import router as worker_apps_router
from src.core.config import get_settings
from src.core.logging_config import configure_logging, trace_id_ctx
from src.core.models.db_helper import db_helper

# Configure logging based on environment settings early during startup
settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events for the application.
    """
    # Startup
    settings = get_settings()
    configure_logging()
    logger.info("Starting Chatico Mapper App...")

    # Initialize database
    try:
        # Test database connection
        async with db_helper.engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection successful")
        app.state.health_snapshot = {
            "status": "healthy",
            "services": {"database": "healthy"},
        }
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        app.state.health_snapshot = {
            "status": "degraded",
            "services": {"database": "unhealthy", "detail": str(e)},
        }
        raise

    logger.info(
        f"Chatico Mapper App started successfully on {settings.host}:{settings.port}"
    )

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
        description="Auth management and Instagram webhook mapper for routing comments to worker applications",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # ========================================
    # Middleware
    # ========================================

    # CORS middleware (configurable for proxy setups like nginx)
    if settings.cors.enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=settings.cors_allow_methods,
            allow_headers=settings.cors_allow_headers,
        )

    # ========================================
    # Routers
    # ========================================

    # Include API routers
    app.include_router(webhook_router, prefix="/api/v1")
    app.include_router(worker_apps_router, prefix="/api/v1")
    app.include_router(google_oauth_router, prefix="/api/v1")
    app.include_router(instagram_oauth_router, prefix="/api/v1")
    app.include_router(auth_router)
    app.include_router(users_router, prefix="/api/v1")

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
    async def health(request: Request):
        """
        Health check endpoint.

        Returns:
            Health status of the application and its dependencies
        """
        snapshot = getattr(request.app.state, "health_snapshot", None)
        if snapshot is None:
            snapshot = {
                "status": "unknown",
                "services": {},
            }
        return snapshot

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


# Middleware для проверки X-Hub подписи
@app.middleware("http")
async def verify_webhook_signature(request: Request, call_next):
    # Assign/propagate a trace id for each request
    incoming_trace = request.headers.get("X-Trace-Id")
    trace_id = incoming_trace or str(uuid.uuid4())
    token = trace_id_ctx.set(trace_id)
    try:
        request.state.trace_id = trace_id
        # Check if this is a POST request to the webhook endpoint (with or without trailing slash)
        webhook_path = "/api/v1/webhook"
        if request.method == "POST" and request.url.path.rstrip("/") == webhook_path:
            # Instagram uses X-Hub-Signature-256 (SHA256) instead of X-Hub-Signature (SHA1)
            signature_256 = request.headers.get("X-Hub-Signature-256")
            signature_1 = request.headers.get("X-Hub-Signature")
            body = await request.body()

            # Try SHA256 first (Instagram's preferred method), then fallback to SHA1
            signature = signature_256 or signature_1

            if signature:
                # Determine which algorithm to use based on the header
                if signature_256:
                    # Instagram uses SHA256
                    expected_signature = (
                        "sha256="
                        + hmac.new(
                            settings.app_secret.encode(), body, hashlib.sha256
                        ).hexdigest()
                    )
                else:
                    # Fallback to SHA1 for compatibility
                    expected_signature = (
                        "sha1="
                        + hmac.new(
                            settings.app_secret.encode(), body, hashlib.sha1
                        ).hexdigest()
                    )

                if not hmac.compare_digest(signature, expected_signature):
                    logging.error("Signature verification failed!")
                    logging.error(f"Body length: {len(body)}")
                    logging.error(
                        f"Signature header used: {'X-Hub-Signature-256' if signature_256 else 'X-Hub-Signature'}"
                    )
                    logging.error(
                        f"Signature prefix: {signature[:10]}..."
                        if len(signature) > 10
                        else "Signature: [REDACTED]"
                    )
                    return JSONResponse(
                        status_code=401, content={"detail": "Invalid signature"}
                    )
                else:
                    logging.info("Signature verification successful")
            else:
                # Check if we're in development mode (allow requests without signature for testing)
                development_mode = (
                    os.getenv("DEVELOPMENT_MODE", "false").lower() == "true"
                )

                if development_mode:
                    logging.warning(
                        "DEVELOPMENT MODE: Allowing webhook request without signature header"
                    )
                else:
                    # Block requests without signature headers in production
                    logging.error(
                        "Webhook request received without X-Hub-Signature or X-Hub-Signature-256 header - blocking request"
                    )
                    return JSONResponse(
                        status_code=401, content={"detail": "Missing signature header"}
                    )

            # Сохраняем тело запроса для дальнейшей обработки
            request.state.body = body
            response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers["X-Trace-Id"] = trace_id
        return response
    finally:
        trace_id_ctx.reset(token)


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
