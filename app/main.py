"""Main FastAPI application for Chatico Mapper App."""

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api import router
from app.config import settings
from app.dependencies import container


# Configure structured logging
def configure_logging():
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, settings.log_level.upper()),
        stream=sys.stdout,
    )


# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    # Startup
    configure_logging()
    logger = structlog.get_logger(__name__)
    logger.info("Starting Chatico Mapper App", version=settings.app_version)

    # Initialize database connection
    try:
        await container.database_session().connect()
        logger.info("Database connection established")
    except Exception as e:
        logger.error("Failed to connect to database", error=str(e))
        raise

    # Initialize RabbitMQ connection
    try:
        rabbitmq_service = container.rabbitmq_service()
        await rabbitmq_service.connect()
        logger.info("RabbitMQ connection established")
    except Exception as e:
        logger.error("Failed to connect to RabbitMQ", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("Shutting down Chatico Mapper App")

    # Close RabbitMQ connection
    try:
        rabbitmq_service = container.rabbitmq_service()
        await rabbitmq_service.disconnect()
        logger.info("RabbitMQ connection closed")
    except Exception as e:
        logger.error("Error closing RabbitMQ connection", error=str(e))

    # Close database connection
    try:
        await container.database_session().disconnect()
        logger.info("Database connection closed")
    except Exception as e:
        logger.error("Error closing database connection", error=str(e))


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Instagram Webhook Proxy Router with RabbitMQ Integration",
    debug=settings.debug,
    lifespan=lifespan,
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"],  # Configure appropriately for production
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Add request size validation middleware
@app.middleware("http")
async def validate_request_size(request: Request, call_next):
    """Validate request size."""
    if request.method == "POST" and request.url.path.endswith("/webhook"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 1024 * 1024:  # 1MB limit
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Request too large",
            )

    response = await call_next(request)
    return response


# Include API routes
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Chatico Mapper App",
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "version": settings.app_version}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
