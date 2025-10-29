"""Use cases for Chatico Mapper App."""

import time
from typing import Dict, List, Optional
from uuid import uuid4

import structlog

from app.models import WorkerApp
from app.repositories import WebhookLogRepository, WorkerAppRepository
from app.schemas import (
    InstagramWebhookPayload,
    RoutingResponse,
    WorkerAppCreate,
    WorkerAppListResponse,
    WorkerAppResponse,
    WorkerAppUpdate,
    WebhookLogListResponse,
)
from app.services import (
    InstagramService,
    RabbitMQService,
    RoutingService,
    WebhookLoggingService,
)

logger = structlog.get_logger()


class ProcessWebhookUseCase:
    """Use case for processing Instagram webhooks."""

    def __init__(
        self,
        instagram_service: InstagramService,
        rabbitmq_service: RabbitMQService,
        routing_service: RoutingService,
        webhook_logging_service: WebhookLoggingService,
        worker_app_repository: WorkerAppRepository,
    ):
        """Initialize use case with dependencies."""
        self.instagram_service = instagram_service
        self.rabbitmq_service = rabbitmq_service
        self.routing_service = routing_service
        self.webhook_logging_service = webhook_logging_service
        self.worker_app_repository = worker_app_repository

    async def execute(
        self, webhook_payload: InstagramWebhookPayload, webhook_id: str
    ) -> RoutingResponse:
        """Process Instagram webhook and route to appropriate worker app."""
        start_time = time.time()

        try:
            # Extract media IDs from webhook
            media_ids = await self.routing_service.extract_media_ids_from_webhook(
                webhook_payload
            )

            if not media_ids:
                logger.warning("No media IDs found in webhook", webhook_id=webhook_id)
                await self.webhook_logging_service.log_webhook_processing(
                    webhook_id=webhook_id,
                    owner_id="unknown",
                    worker_app_id=None,
                    target_app_name=None,
                    status="failed",
                    error_message="No media IDs found in webhook",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

                return RoutingResponse(
                    status="failed",
                    message="No media IDs found in webhook",
                    webhook_id=webhook_id,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

            # Get media information and extract owner IDs
            media_info = await self.instagram_service.batch_get_media_info(media_ids)
            owner_ids = set()

            for media_id, media in media_info.items():
                if media:
                    try:
                        owner_id = self.instagram_service.extract_owner_id(media)
                        owner_ids.add(owner_id)
                    except ValueError as e:
                        logger.warning(
                            "Failed to extract owner ID",
                            webhook_id=webhook_id,
                            media_id=media_id,
                            error=str(e),
                        )

            if not owner_ids:
                logger.warning(
                    "No owner IDs found from media",
                    webhook_id=webhook_id,
                    media_ids=media_ids,
                )
                await self.webhook_logging_service.log_webhook_processing(
                    webhook_id=webhook_id,
                    owner_id="unknown",
                    worker_app_id=None,
                    target_app_name=None,
                    status="failed",
                    error_message="No owner IDs found from media",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

                return RoutingResponse(
                    status="failed",
                    message="No owner IDs found from media",
                    webhook_id=webhook_id,
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

            # Route webhook to worker apps for each owner
            routing_results = []
            for owner_id in owner_ids:
                result = await self._route_to_worker_app(
                    webhook_payload, owner_id, webhook_id, start_time
                )
                routing_results.append(result)

            # Determine overall status
            successful_routes = [r for r in routing_results if r["status"] == "success"]
            failed_routes = [r for r in routing_results if r["status"] == "failed"]

            if successful_routes:
                status = "success"
                message = f"Webhook routed to {len(successful_routes)} worker app(s)"
                routed_to = ", ".join([r["app_name"] for r in successful_routes])
            else:
                status = "failed"
                message = "Failed to route webhook to any worker app"
                routed_to = None

            processing_time_ms = int((time.time() - start_time) * 1000)

            return RoutingResponse(
                status=status,
                message=message,
                routed_to=routed_to,
                processing_time_ms=processing_time_ms,
                webhook_id=webhook_id,
            )

        except Exception as e:
            logger.error(
                "Unexpected error processing webhook",
                webhook_id=webhook_id,
                error=str(e),
            )

            await self.webhook_logging_service.log_webhook_processing(
                webhook_id=webhook_id,
                owner_id="unknown",
                worker_app_id=None,
                target_app_name=None,
                status="failed",
                error_message=f"Unexpected error: {str(e)}",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

            return RoutingResponse(
                status="failed",
                message=f"Unexpected error: {str(e)}",
                webhook_id=webhook_id,
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

    async def _route_to_worker_app(
        self,
        webhook_payload: InstagramWebhookPayload,
        owner_id: str,
        webhook_id: str,
        start_time: float,
    ) -> Dict:
        """Route webhook to worker app for specific owner."""
        try:
            # Find worker app for owner
            worker_app = await self.routing_service.find_worker_app(owner_id)

            if not worker_app:
                logger.warning(
                    "No worker app found for owner",
                    owner_id=owner_id,
                    webhook_id=webhook_id,
                )

                await self.webhook_logging_service.log_webhook_processing(
                    webhook_id=webhook_id,
                    owner_id=owner_id,
                    worker_app_id=None,
                    target_app_name=None,
                    status="failed",
                    error_message="No worker app found for owner",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                )

                return {
                    "status": "failed",
                    "app_name": None,
                    "error": "No worker app found for owner",
                }

            # Create routing request
            routing_request = await self.routing_service.create_routing_request(
                webhook_payload, owner_id, worker_app, webhook_id
            )

            # Publish to RabbitMQ
            success = await self.rabbitmq_service.publish_message(
                worker_app["queue_name"], routing_request
            )

            processing_time_ms = int((time.time() - start_time) * 1000)

            if success:
                await self.webhook_logging_service.log_webhook_processing(
                    webhook_id=webhook_id,
                    owner_id=owner_id,
                    worker_app_id=worker_app["id"],
                    target_app_name=worker_app["app_name"],
                    status="routed",
                    processing_time_ms=processing_time_ms,
                )

                return {
                    "status": "success",
                    "app_name": worker_app["app_name"],
                    "error": None,
                }
            else:
                await self.webhook_logging_service.log_webhook_processing(
                    webhook_id=webhook_id,
                    owner_id=owner_id,
                    worker_app_id=worker_app["id"],
                    target_app_name=worker_app["app_name"],
                    status="failed",
                    error_message="Failed to publish message to RabbitMQ",
                    processing_time_ms=processing_time_ms,
                )

                return {
                    "status": "failed",
                    "app_name": worker_app["app_name"],
                    "error": "Failed to publish message to RabbitMQ",
                }

        except Exception as e:
            logger.error(
                "Error routing to worker app",
                owner_id=owner_id,
                webhook_id=webhook_id,
                error=str(e),
            )

            await self.webhook_logging_service.log_webhook_processing(
                webhook_id=webhook_id,
                owner_id=owner_id,
                worker_app_id=None,
                target_app_name=None,
                status="failed",
                error_message=f"Routing error: {str(e)}",
                processing_time_ms=int((time.time() - start_time) * 1000),
            )

            return {
                "status": "failed",
                "app_name": None,
                "error": f"Routing error: {str(e)}",
            }


class ManageWorkerAppsUseCase:
    """Use case for managing worker app configurations."""

    def __init__(
        self,
        worker_app_repository: WorkerAppRepository,
        rabbitmq_service: RabbitMQService,
    ):
        """Initialize use case with dependencies."""
        self.worker_app_repository = worker_app_repository
        self.rabbitmq_service = rabbitmq_service

    async def create_worker_app(
        self, worker_app_data: WorkerAppCreate
    ) -> WorkerAppResponse:
        """Create a new worker app."""
        # Check if owner_id already exists
        if await self.worker_app_repository.exists_by_owner_id(
            worker_app_data.owner_id
        ):
            raise ValueError(
                f"Worker app already exists for owner_id: {worker_app_data.owner_id}"
            )

        # Check if queue_name already exists
        if await self.worker_app_repository.exists_by_queue_name(
            worker_app_data.queue_name
        ):
            raise ValueError(f"Queue name already exists: {worker_app_data.queue_name}")

        # Create worker app
        worker_app = WorkerApp(
            owner_id=worker_app_data.owner_id,
            app_name=worker_app_data.app_name,
            base_url=str(worker_app_data.base_url),
            webhook_path=worker_app_data.webhook_path,
            queue_name=worker_app_data.queue_name,
            is_active=worker_app_data.is_active,
        )

        created_app = await self.worker_app_repository.create(worker_app)

        # Create RabbitMQ queue
        await self.rabbitmq_service.create_queue(worker_app_data.queue_name)

        logger.info(
            "Worker app created",
            app_id=str(created_app.id),
            owner_id=created_app.owner_id,
            app_name=created_app.app_name,
        )

        return WorkerAppResponse.model_validate(created_app)

    async def get_worker_app(self, app_id: str) -> Optional[WorkerAppResponse]:
        """Get worker app by ID."""
        worker_app = await self.worker_app_repository.get_by_id(app_id)
        if not worker_app:
            return None
        return WorkerAppResponse.model_validate(worker_app)

    async def list_worker_apps(
        self, skip: int = 0, limit: int = 100, active_only: bool = False
    ) -> WorkerAppListResponse:
        """List worker apps with pagination."""
        apps = await self.worker_app_repository.get_all(skip, limit, active_only)
        total = await self.worker_app_repository.count(active_only)

        return WorkerAppListResponse(
            items=[WorkerAppResponse.model_validate(app) for app in apps],
            total=total,
            page=skip // limit + 1,
            size=limit,
        )

    async def update_worker_app(
        self, app_id: str, update_data: WorkerAppUpdate
    ) -> Optional[WorkerAppResponse]:
        """Update worker app."""
        # Get existing app
        existing_app = await self.worker_app_repository.get_by_id(app_id)
        if not existing_app:
            return None

        # Check queue name uniqueness if being updated
        if update_data.queue_name and update_data.queue_name != existing_app.queue_name:
            if await self.worker_app_repository.exists_by_queue_name(
                update_data.queue_name
            ):
                raise ValueError(f"Queue name already exists: {update_data.queue_name}")

        # Prepare update data
        update_kwargs = {}
        if update_data.app_name is not None:
            update_kwargs["app_name"] = update_data.app_name
        if update_data.base_url is not None:
            update_kwargs["base_url"] = str(update_data.base_url)
        if update_data.webhook_path is not None:
            update_kwargs["webhook_path"] = update_data.webhook_path
        if update_data.queue_name is not None:
            update_kwargs["queue_name"] = update_data.queue_name
        if update_data.is_active is not None:
            update_kwargs["is_active"] = update_data.is_active

        # Update app
        updated_app = await self.worker_app_repository.update(app_id, **update_kwargs)
        if not updated_app:
            return None

        # Create new queue if queue name changed
        if update_data.queue_name and update_data.queue_name != existing_app.queue_name:
            await self.rabbitmq_service.create_queue(update_data.queue_name)

        logger.info(
            "Worker app updated",
            app_id=str(updated_app.id),
            owner_id=updated_app.owner_id,
            app_name=updated_app.app_name,
        )

        return WorkerAppResponse.model_validate(updated_app)

    async def delete_worker_app(self, app_id: str) -> bool:
        """Delete worker app."""
        # Get app info before deletion
        app = await self.worker_app_repository.get_by_id(app_id)
        if not app:
            return False

        # Delete app
        success = await self.worker_app_repository.delete(app_id)

        if success:
            logger.info(
                "Worker app deleted",
                app_id=str(app.id),
                owner_id=app.owner_id,
                app_name=app.app_name,
            )

        return success

    async def get_worker_app_by_owner_id(
        self, owner_id: str
    ) -> Optional[WorkerAppResponse]:
        """Get worker app by owner ID."""
        worker_app = await self.worker_app_repository.get_by_owner_id(owner_id)
        if not worker_app:
            return None
        return WorkerAppResponse.model_validate(worker_app)

    async def toggle_worker_app_status(
        self, app_id: str
    ) -> Optional[WorkerAppResponse]:
        """Toggle worker app active status."""
        app = await self.worker_app_repository.get_by_id(app_id)
        if not app:
            return None

        updated_app = await self.worker_app_repository.update(
            app_id, is_active=not app.is_active
        )

        if updated_app:
            logger.info(
                "Worker app status toggled",
                app_id=str(updated_app.id),
                owner_id=updated_app.owner_id,
                is_active=updated_app.is_active,
            )

        return WorkerAppResponse.model_validate(updated_app) if updated_app else None

    async def bulk_toggle_worker_apps(self, app_ids: List[str]) -> Dict[str, str]:
        """Bulk toggle worker app status."""
        results = {}

        for app_id in app_ids:
            try:
                updated_app = await self.toggle_worker_app_status(app_id)
                if updated_app:
                    results[app_id] = "success"
                else:
                    results[app_id] = "not_found"
            except Exception as e:
                logger.error(
                    "Error toggling worker app in bulk operation",
                    app_id=app_id,
                    error=str(e),
                )
                results[app_id] = f"error: {str(e)}"

        logger.info(
            "Bulk toggle worker apps completed",
            total_apps=len(app_ids),
            successful=sum(1 for status in results.values() if status == "success"),
        )

        return results


class WebhookLoggingUseCase:
    """Use case for webhook logging operations."""

    def __init__(self, webhook_log_repository: WebhookLogRepository):
        """Initialize use case with dependencies."""
        self.webhook_log_repository = webhook_log_repository

    async def get_webhook_logs(
        self,
        skip: int = 0,
        limit: int = 100,
        owner_id: Optional[str] = None,
        status: Optional[str] = None,
        worker_app_id: Optional[str] = None,
    ) -> WebhookLogListResponse:
        """Get webhook logs with filtering and pagination."""
        logs = await self.webhook_log_repository.get_all(
            skip, limit, owner_id, status, worker_app_id
        )
        total = await self.webhook_log_repository.count(owner_id, status, worker_app_id)

        from app.schemas import WebhookLogResponse

        return WebhookLogListResponse(
            items=[WebhookLogResponse.model_validate(log) for log in logs],
            total=total,
            page=skip // limit + 1,
            size=limit,
        )

    async def get_webhook_stats(self) -> Dict:
        """Get webhook processing statistics."""
        return await self.webhook_log_repository.get_stats_by_owner_id("all")

    async def get_worker_app_stats(self, worker_app_id: str) -> Dict:
        """Get webhook statistics for specific worker app."""
        return await self.webhook_log_repository.get_stats_by_worker_app(worker_app_id)

    async def cleanup_old_logs(self, days: int = 30) -> int:
        """Clean up old webhook logs."""
        return await self.webhook_log_repository.cleanup_old_logs(days)
