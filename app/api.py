"""FastAPI endpoints for Chatico Mapper App."""

import time
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

from app.dependencies import (
    get_database_session,
    get_manage_worker_apps_use_case,
    get_process_webhook_use_case,
    get_rabbitmq_service,
    get_routing_service,
    get_webhook_logging_use_case,
)
from app.schemas import (
    ErrorResponse,
    HealthResponse,
    InstagramWebhookPayload,
    MetricsResponse,
    RoutingResponse,
    WorkerAppCreate,
    WorkerAppListResponse,
    WorkerAppResponse,
    WorkerAppUpdate,
    WebhookLogListResponse,
)
from app.use_cases import (
    ManageWorkerAppsUseCase,
    ProcessWebhookUseCase,
    WebhookLoggingUseCase,
)
from app.services import RabbitMQService, RoutingService
from app.config import settings

logger = structlog.get_logger()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create routers
webhook_router = APIRouter(prefix="/webhook", tags=["webhook"])
worker_apps_router = APIRouter(prefix="/worker-apps", tags=["worker-apps"])
monitoring_router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@webhook_router.post("/", response_model=RoutingResponse)
@limiter.limit("10/minute")
async def process_webhook(
    request: Request,
    webhook_payload: InstagramWebhookPayload,
    process_use_case: ProcessWebhookUseCase = Depends(get_process_webhook_use_case),
    routing_service: RoutingService = Depends(get_routing_service),
) -> RoutingResponse:
    """Process Instagram webhook and route to appropriate worker app."""
    webhook_id = str(uuid4())

    try:
        # Get request body for signature validation
        body = await request.body()

        # Validate webhook signature
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not await routing_service.validate_webhook_signature(body, signature):
            logger.warning(
                "Invalid webhook signature",
                webhook_id=webhook_id,
                signature=signature,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

        # Process webhook
        result = await process_use_case.execute(webhook_payload, webhook_id)

        logger.info(
            "Webhook processed",
            webhook_id=webhook_id,
            status=result.status,
            processing_time_ms=result.processing_time_ms,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error processing webhook",
            webhook_id=webhook_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@webhook_router.get("/")
async def webhook_verification(
    request: Request,
    hub_mode: str,
    hub_challenge: str,
    hub_verify_token: str,
) -> str:
    """Handle Instagram webhook verification challenge."""
    if hub_mode == "subscribe" and hub_verify_token == settings.webhook_verify_token:
        logger.info("Webhook verification successful")
        return hub_challenge
    else:
        logger.warning(
            "Webhook verification failed",
            hub_mode=hub_mode,
            hub_verify_token=hub_verify_token,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )


@worker_apps_router.post(
    "/", response_model=WorkerAppResponse, status_code=status.HTTP_201_CREATED
)
async def create_worker_app(
    worker_app_data: WorkerAppCreate,
    manage_use_case: ManageWorkerAppsUseCase = Depends(get_manage_worker_apps_use_case),
) -> WorkerAppResponse:
    """Create a new worker app configuration."""
    try:
        return await manage_use_case.create_worker_app(worker_app_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Error creating worker app", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@worker_apps_router.get("/", response_model=WorkerAppListResponse)
async def list_worker_apps(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    manage_use_case: ManageWorkerAppsUseCase = Depends(get_manage_worker_apps_use_case),
) -> WorkerAppListResponse:
    """List all worker app configurations."""
    try:
        return await manage_use_case.list_worker_apps(skip, limit, active_only)
    except Exception as e:
        logger.error("Error listing worker apps", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@worker_apps_router.get("/{app_id}", response_model=WorkerAppResponse)
async def get_worker_app(
    app_id: str,
    manage_use_case: ManageWorkerAppsUseCase = Depends(get_manage_worker_apps_use_case),
) -> WorkerAppResponse:
    """Get worker app by ID."""
    try:
        worker_app = await manage_use_case.get_worker_app(app_id)
        if not worker_app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker app not found",
            )
        return worker_app
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting worker app", app_id=app_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@worker_apps_router.put("/{app_id}", response_model=WorkerAppResponse)
async def update_worker_app(
    app_id: str,
    update_data: WorkerAppUpdate,
    manage_use_case: ManageWorkerAppsUseCase = Depends(get_manage_worker_apps_use_case),
) -> WorkerAppResponse:
    """Update worker app configuration."""
    try:
        worker_app = await manage_use_case.update_worker_app(app_id, update_data)
        if not worker_app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker app not found",
            )
        return worker_app
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating worker app", app_id=app_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@worker_apps_router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_worker_app(
    app_id: str,
    manage_use_case: ManageWorkerAppsUseCase = Depends(get_manage_worker_apps_use_case),
) -> None:
    """Delete worker app configuration."""
    try:
        success = await manage_use_case.delete_worker_app(app_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker app not found",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting worker app", app_id=app_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@worker_apps_router.post("/{app_id}/toggle", response_model=WorkerAppResponse)
async def toggle_worker_app_status(
    app_id: str,
    manage_use_case: ManageWorkerAppsUseCase = Depends(get_manage_worker_apps_use_case),
) -> WorkerAppResponse:
    """Toggle worker app active status."""
    try:
        worker_app = await manage_use_case.toggle_worker_app_status(app_id)
        if not worker_app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker app not found",
            )
        return worker_app
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error toggling worker app status", app_id=app_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@worker_apps_router.post("/bulk/toggle", response_model=Dict[str, str])
async def bulk_toggle_worker_apps(
    app_ids: List[str],
    manage_use_case: ManageWorkerAppsUseCase = Depends(get_manage_worker_apps_use_case),
) -> Dict[str, str]:
    """Bulk toggle worker app status."""
    try:
        results = await manage_use_case.bulk_toggle_worker_apps(app_ids)
        return results
    except Exception as e:
        logger.error("Error bulk toggling worker apps", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@worker_apps_router.get("/owner/{owner_id}", response_model=WorkerAppResponse)
async def get_worker_app_by_owner_id(
    owner_id: str,
    manage_use_case: ManageWorkerAppsUseCase = Depends(get_manage_worker_apps_use_case),
) -> WorkerAppResponse:
    """Get worker app by owner ID."""
    try:
        worker_app = await manage_use_case.get_worker_app_by_owner_id(owner_id)
        if not worker_app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Worker app not found",
            )
        return worker_app
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error getting worker app by owner", owner_id=owner_id, error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@monitoring_router.get("/health", response_model=HealthResponse)
async def health_check(
    rabbitmq_service: RabbitMQService = Depends(get_rabbitmq_service),
) -> HealthResponse:
    """Health check endpoint."""
    services = {}

    # Check RabbitMQ
    try:
        await rabbitmq_service.connect()
        services["rabbitmq"] = "healthy"
        await rabbitmq_service.disconnect()
    except Exception as e:
        services["rabbitmq"] = f"unhealthy: {str(e)}"

    # Check database
    try:
        from app.dependencies import get_database_session

        session = get_database_session()
        await session.execute("SELECT 1")
        await session.close()
        services["database"] = "healthy"
    except Exception as e:
        services["database"] = f"unhealthy: {str(e)}"

    # Determine overall status
    overall_status = (
        "healthy"
        if all("healthy" in status for status in services.values())
        else "unhealthy"
    )

    return HealthResponse(
        status=overall_status,
        timestamp=time.time(),
        version=settings.app_version,
        services=services,
    )


@monitoring_router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    webhook_logging_use_case: WebhookLoggingUseCase = Depends(
        get_webhook_logging_use_case
    ),
    manage_use_case: ManageWorkerAppsUseCase = Depends(get_manage_worker_apps_use_case),
    rabbitmq_service: RabbitMQService = Depends(get_rabbitmq_service),
) -> MetricsResponse:
    """Get application metrics."""
    try:
        # Get webhook stats
        webhook_stats = await webhook_logging_use_case.get_webhook_stats()

        # Get worker app counts
        worker_apps_total = await manage_use_case.list_worker_apps(limit=1000)
        worker_apps_active = await manage_use_case.list_worker_apps(
            limit=1000, active_only=True
        )

        # Get RabbitMQ queue info (simplified)
        rabbitmq_queues = {}
        try:
            await rabbitmq_service.connect()
            # This would be implemented to get actual queue sizes
            rabbitmq_queues = {"webhook_queues": 0}
            await rabbitmq_service.disconnect()
        except Exception:
            rabbitmq_queues = {"error": "Unable to connect to RabbitMQ"}

        return MetricsResponse(
            webhook_total=webhook_stats.get("total", 0),
            webhook_success=webhook_stats.get("success", 0),
            webhook_failed=webhook_stats.get("failed", 0),
            webhook_routed=webhook_stats.get("routed", 0),
            avg_processing_time_ms=webhook_stats.get("avg_processing_time_ms", 0),
            worker_apps_active=worker_apps_active.total,
            worker_apps_total=worker_apps_total.total,
            rabbitmq_queues=rabbitmq_queues,
        )

    except Exception as e:
        logger.error("Error getting metrics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@monitoring_router.get("/webhook-logs", response_model=WebhookLogListResponse)
async def get_webhook_logs(
    skip: int = 0,
    limit: int = 100,
    owner_id: Optional[str] = None,
    status: Optional[str] = None,
    worker_app_id: Optional[str] = None,
    webhook_logging_use_case: WebhookLoggingUseCase = Depends(
        get_webhook_logging_use_case
    ),
) -> WebhookLogListResponse:
    """Get webhook processing logs."""
    try:
        return await webhook_logging_use_case.get_webhook_logs(
            skip, limit, owner_id, status, worker_app_id
        )
    except Exception as e:
        logger.error("Error getting webhook logs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


# Error handlers
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error="HTTPException",
            message=exc.detail,
            details={"status_code": exc.status_code},
        ).model_dump(),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle general exceptions."""
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="InternalServerError",
            message="An unexpected error occurred",
            details={"error": str(exc)},
        ).model_dump(),
    )


# Create main router
router = APIRouter()
router.include_router(webhook_router)
router.include_router(worker_apps_router)
router.include_router(monitoring_router)
