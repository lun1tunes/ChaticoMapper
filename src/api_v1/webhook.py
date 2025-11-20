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
from src.core.logging_config import trace_id_ctx
from src.core.use_cases.process_webhook_use_case import ProcessWebhookUseCase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.get("", response_class=PlainTextResponse)
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

    if verification.hub_verify_token != settings.instagram.verify_token:
        logger.warning("Invalid webhook verify token")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid verify token",
        )

    logger.info("Webhook verification successful")
    return PlainTextResponse(
        content=verification.hub_challenge, status_code=status.HTTP_200_OK
    )


@router.post("", response_model=RoutingResponse)
async def process_webhook(
    webhook_payload: WebhookPayload,
    request: Request,
    process_webhook_uc: Annotated[
        ProcessWebhookUseCase, Depends(get_process_webhook_use_case)
    ],
) -> RoutingResponse:
    """Process Instagram comment webhook notifications."""
    trace_id = (
        getattr(request.state, "trace_id", None)
        or trace_id_ctx.get()
        or request.headers.get("X-Trace-ID")
        or "unknown"
    )
    logger.info(
        "Received webhook | trace_id=%s | entries=%s",
        trace_id,
        len(webhook_payload.entry),
    )

    payload_dict = webhook_payload.model_dump(by_alias=True)
    original_headers = {key: value for key, value in request.headers.items()}
    raw_payload: bytes | None = getattr(request.state, "body", None)
    if raw_payload is None:
        raw_payload = await request.body()

    try:
        result = await process_webhook_uc.execute(
            webhook_payload=payload_dict,
            original_headers=original_headers,
            raw_payload=raw_payload,
        )
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Unexpected error processing webhook: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {exc}",
        ) from exc

    last_success = result.get("last_success") or {}
    duplicates = result.get("duplicates", 0) or 0

    if result.get("success"):
        logger.info(
            "Webhook processed successfully | processed=%s | skipped=%s",
            result.get("comments_processed"),
            result.get("comments_skipped"),
        )
        message = f"Processed {result.get('comments_processed', 0)} comment(s)"
        if duplicates:
            message += f" (duplicates ignored: {duplicates})"
        return RoutingResponse(
            status="success",
            message=message,
            routed_to=last_success.get("worker_app_username"),
            processing_time_ms=last_success.get("processing_time_ms"),
            error_details=None,
            webhook_id=trace_id,
        )

    errors = result.get("errors") or []
    error_msg = "; ".join(errors) if errors else "Processing failed"
    logger.error("Webhook processing failed | errors=%s", error_msg)
    return RoutingResponse(
        status="failed",
        message="Webhook processing failed",
        routed_to=None,
        processing_time_ms=None,
        error_details=error_msg,
        webhook_id=trace_id,
    )
