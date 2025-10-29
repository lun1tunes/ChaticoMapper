"""Use case for forwarding webhooks to worker apps."""

import logging
import time
from typing import Optional
from uuid import uuid4

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.webhook_log import WebhookLog
from src.core.models.worker_app import WorkerApp
from src.core.repositories.webhook_log_repository import WebhookLogRepository

logger = logging.getLogger(__name__)


class ForwardWebhookUseCase:
    """
    Forward webhook payload to worker app.

    Supports both HTTP forwarding and RabbitMQ publishing.
    Creates audit log entries for tracking.
    """

    def __init__(
        self,
        session: AsyncSession,
        http_timeout: float = 30.0,
    ):
        self.session = session
        self.http_timeout = http_timeout
        self.log_repo = WebhookLogRepository(session)

    async def execute(
        self,
        worker_app: WorkerApp,
        webhook_payload: dict,
        owner_id: str,
    ) -> dict:
        """
        Forward webhook to worker app and log result.

        Args:
            worker_app: WorkerApp configuration
            webhook_payload: Original Instagram webhook payload
            owner_id: Instagram account ID

        Returns:
            dict with:
                - success (bool): Whether forwarding succeeded
                - method (str): Forwarding method (http/rabbitmq)
                - status_code (int): HTTP status code (for HTTP method)
                - processing_time_ms (int): Processing time in milliseconds
                - error (str): Error message (if success=False)
        """
        start_time = time.time()
        webhook_id = str(uuid4())

        try:
            # For now, implement HTTP forwarding
            # RabbitMQ can be added later as an alternative
            result = await self._forward_via_http(
                worker_app=worker_app,
                webhook_payload=webhook_payload,
                webhook_id=webhook_id,
            )

            processing_time_ms = int((time.time() - start_time) * 1000)
            result["processing_time_ms"] = processing_time_ms

            # Log the forwarding attempt
            await self._create_log_entry(
                webhook_id=webhook_id,
                owner_id=owner_id,
                worker_app=worker_app,
                result=result,
                processing_time_ms=processing_time_ms,
            )

            return result

        except Exception as e:
            logger.exception(f"Unexpected error forwarding webhook: {e}")
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Log the failure
            await self._create_log_entry(
                webhook_id=webhook_id,
                owner_id=owner_id,
                worker_app=worker_app,
                result={"success": False, "error": str(e)},
                processing_time_ms=processing_time_ms,
            )

            return {
                "success": False,
                "method": "http",
                "error": f"Unexpected error: {str(e)}",
                "processing_time_ms": processing_time_ms,
            }

    async def _forward_via_http(
        self,
        worker_app: WorkerApp,
        webhook_payload: dict,
        webhook_id: str,
    ) -> dict:
        """
        Forward webhook via HTTP POST.

        Args:
            worker_app: WorkerApp configuration
            webhook_payload: Webhook payload to forward
            webhook_id: Unique webhook identifier

        Returns:
            dict with success status and details
        """
        url = worker_app.full_webhook_url

        try:
            async with httpx.AsyncClient(timeout=self.http_timeout) as client:
                response = await client.post(
                    url,
                    json=webhook_payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-ID": webhook_id,
                        "X-Forwarded-From": "chatico-mapper",
                    },
                )

                if response.status_code in (200, 201, 202, 204):
                    logger.info(
                        f"Successfully forwarded webhook to {worker_app.app_name}: "
                        f"status={response.status_code}"
                    )
                    return {
                        "success": True,
                        "method": "http",
                        "status_code": response.status_code,
                        "response_text": response.text[:500] if response.text else None,
                    }
                else:
                    logger.warning(
                        f"Worker app returned non-success status: "
                        f"app={worker_app.app_name}, status={response.status_code}"
                    )
                    return {
                        "success": False,
                        "method": "http",
                        "status_code": response.status_code,
                        "error": f"Worker app returned {response.status_code}",
                        "response_text": response.text[:500] if response.text else None,
                    }

        except httpx.TimeoutException:
            logger.error(f"Timeout forwarding to {worker_app.app_name}")
            return {
                "success": False,
                "method": "http",
                "error": "Request timeout",
            }

        except httpx.RequestError as e:
            logger.error(f"Request error forwarding to {worker_app.app_name}: {e}")
            return {
                "success": False,
                "method": "http",
                "error": f"Request error: {str(e)}",
            }

    async def _create_log_entry(
        self,
        webhook_id: str,
        owner_id: str,
        worker_app: WorkerApp,
        result: dict,
        processing_time_ms: int,
    ) -> None:
        """
        Create audit log entry for webhook forwarding.

        Args:
            webhook_id: Unique webhook identifier
            owner_id: Instagram account ID
            worker_app: WorkerApp configuration
            result: Forwarding result dict
            processing_time_ms: Processing time in milliseconds
        """
        try:
            log_entry = WebhookLog(
                webhook_id=webhook_id,
                owner_id=owner_id,
                worker_app_id=worker_app.id,
                target_app_name=worker_app.app_name,
                processing_status="success" if result.get("success") else "failed",
                error_message=result.get("error"),
                processing_time_ms=processing_time_ms,
            )

            self.session.add(log_entry)
            await self.session.commit()

            logger.debug(f"Created webhook log: webhook_id={webhook_id}")

        except Exception as e:
            logger.error(f"Failed to create webhook log: {e}")
            await self.session.rollback()
