"""Webhook endpoints for Instagram Graph API."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_v1.schemas import InstagramWebhookPayload, RoutingResponse
from src.core.dependencies import get_process_webhook_use_case
from src.core.use_cases.process_webhook_use_case import ProcessWebhookUseCase
from src.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.get("", response_class=PlainTextResponse)
@router.get("/", response_class=PlainTextResponse)
async def verify_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    Instagram webhook verification endpoint.

    When you set up a webhook subscription, Instagram sends a GET request
    to verify that your endpoint is valid. This endpoint handles that verification.

    Query Parameters:
        hub.mode: Should be 'subscribe'
        hub.challenge: Random string to echo back
        hub.verify_token: Token that should match your configured verify token

    Returns:
        The hub.challenge value if verification succeeds
        403 error if verification fails
    """
    hub_mode = request.query_params.get("hub.mode")
    hub_challenge = request.query_params.get("hub.challenge")
    hub_verify_token = request.query_params.get("hub.verify_token")

    logger.info(
        f"Webhook verification request: mode={hub_mode}, "
        f"verify_token={'***' if hub_verify_token else None}"
    )

    # Validate required parameters
    if not all([hub_mode, hub_challenge, hub_verify_token]):
        logger.warning("Missing required verification parameters")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required parameters: hub.mode, hub.challenge, hub.verify_token"
        )

    # Verify mode
    if hub_mode != "subscribe":
        logger.warning(f"Invalid hub.mode: {hub_mode}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid hub.mode, expected 'subscribe'"
        )

    # Verify token
    expected_token = settings.webhook.verify_token
    if hub_verify_token != expected_token:
        logger.warning("Invalid verify token")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid verify token"
        )

    logger.info("Webhook verification successful")

    # Return challenge to complete verification
    return PlainTextResponse(content=hub_challenge, status_code=200)


@router.post("", response_model=RoutingResponse)
@router.post("/", response_model=RoutingResponse)
async def process_webhook(
    webhook_payload: InstagramWebhookPayload,
    request: Request,
    process_webhook_uc: Annotated[ProcessWebhookUseCase, Depends(get_process_webhook_use_case)],
):
    """
    Process Instagram webhook notifications.

    This endpoint receives comment notifications from Instagram,
    extracts media owner information, routes to appropriate worker app,
    and stores comment data for auditing.

    Request Body:
        Instagram webhook payload with entry and changes

    Returns:
        RoutingResponse with processing status and details
    """
    # Log webhook receipt
    trace_id = request.headers.get("X-Trace-ID", "unknown")
    logger.info(
        f"Received webhook | trace_id={trace_id} | "
        f"entries={len(webhook_payload.entry)}"
    )

    # Process webhook using injected use case
    try:
        result = await process_webhook_uc.execute(webhook_payload.model_dump())

        if result.get("success"):
            logger.info(
                f"Webhook processed successfully | "
                f"processed={result.get('comments_processed')}, "
                f"skipped={result.get('comments_skipped')}"
            )

            return RoutingResponse(
                status="success",
                message=f"Processed {result.get('comments_processed')} comment(s)",
                routed_to=None,  # Could be enhanced to track actual routing
                processing_time_ms=None,
                error_details=None,
                webhook_id=trace_id,
            )
        else:
            errors = result.get("errors", [])
            error_msg = "; ".join(errors) if errors else "Unknown error"

            logger.error(f"Webhook processing failed | errors={error_msg}")

            return RoutingResponse(
                status="failed",
                message="Webhook processing failed",
                routed_to=None,
                processing_time_ms=None,
                error_details=error_msg,
                webhook_id=trace_id,
            )

    except Exception as e:
        logger.exception(f"Unexpected error processing webhook: {e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/health")
async def webhook_health():
    """Quick health check for webhook endpoint."""
    return {"status": "ok", "endpoint": "webhook"}
