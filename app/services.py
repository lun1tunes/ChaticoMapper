"""Core services for Chatico Mapper App."""

import asyncio
import hashlib
import hmac
import json
import time
from typing import Dict, List, Optional, Protocol
from uuid import uuid4

import aio_pika
import httpx
import structlog
from aio_pika import Message, connect_robust
from aio_pika.abc import AbstractConnection, AbstractChannel, AbstractExchange

from app.config import settings
from app.schemas import InstagramMedia, InstagramWebhookPayload, RoutingRequest

logger = structlog.get_logger()


class InstagramServiceProtocol(Protocol):
    """Protocol for Instagram service."""

    async def get_media_info(self, media_id: str) -> Optional[InstagramMedia]:
        """Get media information from Instagram Graph API."""
        ...

    def extract_owner_id(self, media: InstagramMedia) -> str:
        """Extract owner ID from media object."""
        ...


class RabbitMQServiceProtocol(Protocol):
    """Protocol for RabbitMQ service."""

    async def publish_message(self, queue_name: str, message: RoutingRequest) -> bool:
        """Publish message to RabbitMQ queue."""
        ...

    async def setup_queues(self) -> None:
        """Setup RabbitMQ queues and exchanges."""
        ...


class RoutingServiceProtocol(Protocol):
    """Protocol for routing service."""

    async def find_worker_app(self, owner_id: str) -> Optional[Dict]:
        """Find worker app by owner ID."""
        ...

    async def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Validate webhook HMAC signature."""
        ...

    async def check_worker_app_health(self, worker_app: Dict) -> bool:
        """Check if a worker app is healthy and available."""
        ...

    async def get_worker_apps_with_health_status(
        self, worker_apps: List[Dict]
    ) -> List[Dict]:
        """Get worker apps with their health status."""
        ...


class InstagramService:
    """Service for Instagram Graph API operations."""

    def __init__(self):
        """Initialize Instagram service."""
        self.base_url = settings.instagram_api_base_url
        self.access_token = settings.instagram_access_token
        self.timeout = settings.instagram_api_timeout
        self.rate_limit = settings.instagram_rate_limit
        self._rate_limiter = asyncio.Semaphore(self.rate_limit)

    async def get_media_info(self, media_id: str) -> Optional[InstagramMedia]:
        """Get media information from Instagram Graph API."""
        async with self._rate_limiter:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = f"{self.base_url}/{media_id}"
                    params = {
                        "fields": "id,owner,media_type,media_url,permalink",
                        "access_token": self.access_token,
                    }

                    response = await client.get(url, params=params)
                    response.raise_for_status()

                    data = response.json()

                    return InstagramMedia(
                        id=data.get("id"),
                        owner=data.get("owner"),
                        media_type=data.get("media_type"),
                        media_url=data.get("media_url"),
                        permalink=data.get("permalink"),
                    )

            except httpx.HTTPError as e:
                logger.error(
                    "Instagram API error",
                    media_id=media_id,
                    error=str(e),
                    status_code=getattr(e.response, "status_code", None),
                )
                return None
            except Exception as e:
                logger.error(
                    "Unexpected error getting media info",
                    media_id=media_id,
                    error=str(e),
                )
                return None

    def extract_owner_id(self, media: InstagramMedia) -> str:
        """Extract owner ID from media object."""
        if not media or not media.owner:
            raise ValueError("Owner information not found")

        owner_id = media.owner.get("id")
        if not owner_id:
            raise ValueError("Owner ID not found")

        return owner_id

    async def batch_get_media_info(
        self, media_ids: List[str]
    ) -> Dict[str, Optional[InstagramMedia]]:
        """Get media information for multiple media IDs."""
        tasks = [self.get_media_info(media_id) for media_id in media_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        media_info = {}
        for media_id, result in zip(media_ids, results):
            if isinstance(result, Exception):
                logger.error(
                    "Error getting media info",
                    media_id=media_id,
                    error=str(result),
                )
                media_info[media_id] = None
            else:
                media_info[media_id] = result

        return media_info


class RabbitMQService:
    """Service for RabbitMQ operations."""

    def __init__(self):
        """Initialize RabbitMQ service."""
        self.url = settings.rabbitmq_url
        self.exchange_name = settings.rabbitmq_exchange
        self.dlx_name = settings.rabbitmq_dead_letter_exchange
        self.message_ttl = settings.rabbitmq_message_ttl
        self.max_retries = settings.rabbitmq_max_retries

        self._connection: Optional[AbstractConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._exchange: Optional[AbstractExchange] = None
        self._dlx: Optional[AbstractExchange] = None

    async def connect(self) -> None:
        """Connect to RabbitMQ."""
        try:
            self._connection = await connect_robust(self.url)
            self._channel = await self._connection.channel()

            # Enable publisher confirms
            await self._channel.set_qos(prefetch_count=1)
            await self._channel.confirm_delivery()

            # Declare exchanges
            self._exchange = await self._channel.declare_exchange(
                self.exchange_name, aio_pika.ExchangeType.DIRECT, durable=True
            )

            self._dlx = await self._channel.declare_exchange(
                self.dlx_name, aio_pika.ExchangeType.DIRECT, durable=True
            )

            logger.info("Connected to RabbitMQ with publisher confirms enabled")

        except Exception as e:
            logger.error("Failed to connect to RabbitMQ", error=str(e))
            raise

    async def disconnect(self) -> None:
        """Disconnect from RabbitMQ."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("Disconnected from RabbitMQ")

    async def setup_queues(self) -> None:
        """Setup RabbitMQ queues and exchanges."""
        if not self._channel:
            await self.connect()

        # This method will be called by the application to setup specific queues
        # Individual queues will be created dynamically when worker apps are registered
        logger.info("RabbitMQ queues setup completed")

    async def create_queue(self, queue_name: str) -> None:
        """Create a queue for a worker app."""
        if not self._channel:
            await self.connect()

        # Declare queue with dead letter exchange
        queue = await self._channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-message-ttl": self.message_ttl * 1000,  # Convert to milliseconds
                "x-dead-letter-exchange": self.dlx_name,
                "x-max-retries": self.max_retries,
            },
        )

        # Bind queue to exchange
        await queue.bind(self._exchange, queue_name)

        logger.info("Created queue", queue_name=queue_name)

    async def publish_message(self, queue_name: str, message: RoutingRequest) -> bool:
        """Publish message to RabbitMQ queue with retry logic."""
        if not self._channel or not self._exchange:
            await self.connect()

        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                # Create message
                message_body = message.model_dump_json().encode()

                rabbitmq_message = Message(
                    message_body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=str(uuid4()),
                    headers={
                        "webhook_id": message.webhook_id,
                        "owner_id": message.owner_id,
                        "target_app": message.target_app_name,
                        "retry_count": attempt,
                    },
                )

                # Publish with confirmation
                await self._exchange.publish(
                    rabbitmq_message, routing_key=queue_name, mandatory=True
                )

                logger.info(
                    "Message published",
                    queue_name=queue_name,
                    webhook_id=message.webhook_id,
                    owner_id=message.owner_id,
                    attempt=attempt + 1,
                )

                return True

            except Exception as e:
                logger.warning(
                    "Failed to publish message",
                    queue_name=queue_name,
                    webhook_id=message.webhook_id,
                    attempt=attempt + 1,
                    error=str(e),
                )

                if attempt < max_retries - 1:
                    # Exponential backoff
                    delay = base_delay * (2**attempt)
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Failed to publish message after all retries",
                        queue_name=queue_name,
                        webhook_id=message.webhook_id,
                        max_retries=max_retries,
                    )
                    return False

        return False

    async def get_queue_info(self, queue_name: str) -> Optional[Dict]:
        """Get queue information."""
        if not self._channel:
            await self.connect()

        try:
            queue = await self._channel.declare_queue(queue_name, passive=True)
            return {
                "name": queue.name,
                "message_count": queue.declaration_result.message_count,
                "consumer_count": queue.declaration_result.consumer_count,
            }
        except Exception as e:
            logger.error(
                "Failed to get queue info",
                queue_name=queue_name,
                error=str(e),
            )
            return None


class RoutingService:
    """Service for webhook routing logic."""

    def __init__(self, worker_app_repository):
        """Initialize routing service."""
        self.worker_app_repository = worker_app_repository

    async def find_worker_app(self, owner_id: str) -> Optional[Dict]:
        """Find worker app by owner ID."""
        worker_app = await self.worker_app_repository.get_by_owner_id(owner_id)

        if not worker_app:
            return None

        return {
            "id": str(worker_app.id),
            "app_name": worker_app.app_name,
            "base_url": worker_app.base_url,
            "webhook_path": worker_app.webhook_path,
            "queue_name": worker_app.queue_name,
            "is_active": worker_app.is_active,
        }

    async def validate_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Validate webhook HMAC signature."""
        try:
            # Remove 'sha256=' prefix if present
            if signature.startswith("sha256="):
                signature = signature[7:]

            # Create expected signature
            expected_signature = hmac.new(
                settings.webhook_secret.encode(),
                payload,
                hashlib.sha256,
            ).hexdigest()

            # Compare signatures securely
            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            logger.error("Error validating webhook signature", error=str(e))
            return False

    async def extract_media_ids_from_webhook(
        self, webhook_payload: InstagramWebhookPayload
    ) -> List[str]:
        """Extract media IDs from webhook payload."""
        media_ids = []

        for entry in webhook_payload.entry:
            for change in entry.changes:
                if change.get("field") == "comments":
                    comment_data = change.get("value", {})
                    if "media_id" in comment_data:
                        media_ids.append(comment_data["media_id"])

        return media_ids

    async def create_routing_request(
        self,
        webhook_payload: InstagramWebhookPayload,
        owner_id: str,
        worker_app: Dict,
        webhook_id: str,
    ) -> RoutingRequest:
        """Create routing request for RabbitMQ."""
        target_url = f"{worker_app['base_url']}{worker_app['webhook_path']}"

        return RoutingRequest(
            webhook_payload=webhook_payload,
            owner_id=owner_id,
            target_app_url=target_url,
            target_app_name=worker_app["app_name"],
            queue_name=worker_app["queue_name"],
            webhook_id=webhook_id,
        )


class WebhookLoggingService:
    """Service for webhook logging operations."""

    def __init__(self, webhook_log_repository):
        """Initialize webhook logging service."""
        self.webhook_log_repository = webhook_log_repository

    async def log_webhook_processing(
        self,
        webhook_id: str,
        owner_id: str,
        worker_app_id: Optional[str],
        target_app_name: Optional[str],
        status: str,
        error_message: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
    ) -> None:
        """Log webhook processing result."""
        from app.models import WebhookLog

        webhook_log = WebhookLog(
            webhook_id=webhook_id,
            owner_id=owner_id,
            worker_app_id=worker_app_id,
            target_app_name=target_app_name,
            processing_status=status,
            error_message=error_message,
            processing_time_ms=processing_time_ms,
        )

        await self.webhook_log_repository.create(webhook_log)

        logger.info(
            "Webhook processing logged",
            webhook_id=webhook_id,
            owner_id=owner_id,
            status=status,
            processing_time_ms=processing_time_ms,
        )

    async def check_worker_app_health(self, worker_app: Dict) -> bool:
        """Check if a worker app is healthy and available."""
        try:
            import httpx

            # Construct health check URL
            health_url = f"{worker_app['base_url']}/health"

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(health_url)
                return response.status_code == 200

        except Exception as e:
            logger.warning(
                "Worker app health check failed",
                worker_app_id=worker_app.get("id"),
                base_url=worker_app.get("base_url"),
                error=str(e),
            )
            return False

    async def get_worker_apps_with_health_status(
        self, worker_apps: List[Dict]
    ) -> List[Dict]:
        """Get worker apps with their health status."""
        health_tasks = [
            self.check_worker_app_health(worker_app) for worker_app in worker_apps
        ]
        health_results = await asyncio.gather(*health_tasks, return_exceptions=True)

        result = []
        for worker_app, health_result in zip(worker_apps, health_results):
            worker_app_copy = worker_app.copy()
            worker_app_copy["is_healthy"] = (
                health_result is True
                if not isinstance(health_result, Exception)
                else False
            )
            result.append(worker_app_copy)

        return result

    async def get_processing_stats(self) -> Dict:
        """Get webhook processing statistics."""
        total = await self.webhook_log_repository.count()
        success = await self.webhook_log_repository.count(status="success")
        failed = await self.webhook_log_repository.count(status="failed")
        routed = await self.webhook_log_repository.count(status="routed")

        # Get average processing time
        recent_logs = await self.webhook_log_repository.get_recent_logs(hours=24)
        avg_time = 0
        if recent_logs:
            times = [
                log.processing_time_ms for log in recent_logs if log.processing_time_ms
            ]
            if times:
                avg_time = sum(times) / len(times)

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "routed": routed,
            "avg_processing_time_ms": avg_time,
        }
