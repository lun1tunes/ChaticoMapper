"""Webhook endpoints for Instagram Graph API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError

from src.api_v1.schemas import RoutingResponse, WebhookPayload, WebhookVerification
from src.core.config import Settings, get_settings
from src.core.dependencies import get_process_webhook_use_case
from src.core.use_cases.process_webhook_use_case import ProcessWebhookUseCase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.get("", response_class=PlainTextResponse)
@router.get("/", response_class=PlainTextResponse)
async def verify_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PlainTextResponse:
    """Instagram webhook verification endpoint."""
    query_data = {
        "hub_mode": request.query_params.get("hub.mode"),
        "hub_challenge": request.query_params.get("hub.challenge"),
        "hub_verify_token": request.query_params.get("hub.verify_token"),
    }

    try:
        verification = WebhookVerification(**query_data)
    except ValidationError as exc:
        logger.warning("Invalid webhook verification request: %s", exc.errors())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    if verification.hub_verify_token != settings.webhook.verify_token:
        logger.warning("Invalid webhook verify token")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid verify token",
        )

    logger.info("Webhook verification successful")
    return PlainTextResponse(content=verification.hub_challenge, status_code=status.HTTP_200_OK)


@router.post("", response_model=RoutingResponse)
@router.post("/", response_model=RoutingResponse)
async def process_webhook(
    webhook_payload: WebhookPayload,
    request: Request,
    process_webhook_uc: Annotated[ProcessWebhookUseCase, Depends(get_process_webhook_use_case)],
) -> RoutingResponse:
    """Process Instagram comment webhook notifications."""
    trace_id = request.headers.get("X-Trace-ID", "unknown")
    logger.info(
        "Received webhook | trace_id=%s | entries=%s",
        trace_id,
        len(webhook_payload.entry),
    )

    payload_dict = webhook_payload.model_dump(by_alias=True)

    try:
        result = await process_webhook_uc.execute(payload_dict)
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Unexpected error processing webhook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {exc}",
        ) from exc

    if result.get("success"):
        logger.info(
            "Webhook processed successfully | processed=%s | skipped=%s",
            result.get("comments_processed"),
            result.get("comments_skipped"),
        )
        return RoutingResponse(
            status="success",
            message=f"Processed {result.get('comments_processed')} comment(s)",
            routed_to=None,
            processing_time_ms=None,
            error_details=None,
            webhook_id=trace_id,
        )

    errors = result.get("errors", [])
    error_msg = "; ".join(errors) if errors else "Unknown error"
    logger.error("Webhook processing failed | errors=%s", error_msg)
    return RoutingResponse(
        status="failed",
        message="Webhook processing failed",
        routed_to=None,
        processing_time_ms=None,
        error_details=error_msg,
        webhook_id=trace_id,
    )


@router.get("/health")
async def webhook_health() -> dict[str, str]:
    """Quick health check for webhook endpoint."""
    return {"status": "ok", "endpoint": "webhook"}
