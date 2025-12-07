"""Google/YouTube OAuth endpoints."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import time
from typing import Annotated, Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from src.core.config import Settings, get_settings
from src.core.dependencies import get_oauth_token_service
from src.core.services.oauth_token_service import OAuthTokenService
from src.core.services.youtube_service import YouTubeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["google-oauth"])

CONSENT_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
STATE_TTL_SECONDS = 600


def _sign_state(payload: str, app_secret: str) -> str:
    digest = hmac.new(
        app_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def _generate_state(app_secret: str) -> str:
    nonce = str(uuid4())
    expires_at = int(time.time()) + STATE_TTL_SECONDS
    payload = f"{nonce}:{expires_at}"
    signature = _sign_state(payload, app_secret)
    return f"{payload}:{signature}"


def _validate_state(state: str, app_secret: str) -> None:
    try:
        nonce, exp_str, signature = state.split(":")
        payload = f"{nonce}:{exp_str}"
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter"
        )

    expected_sig = _sign_state(payload, app_secret)
    if not hmac.compare_digest(signature, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state signature"
        )

    try:
        expires_at = int(exp_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter"
        )

    if expires_at < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Expired state parameter"
        )


@router.get("/authorize", response_class=RedirectResponse)
async def authorize(
    settings: Annotated[Settings, Depends(get_settings)],
    redirect_to: Optional[str] = None,
) -> RedirectResponse:
    """Build the Google consent screen URL and redirect the user."""
    state = _generate_state(settings.oauth_app_secret)

    params = {
        "client_id": settings.youtube_client_id,
        "redirect_uri": settings.youtube_redirect_uri,
        "response_type": "code",
        "scope": CONSENT_SCOPE,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    if redirect_to:
        params["redirect_to"] = redirect_to

    query = str(httpx.QueryParams(params))
    consent_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
    return RedirectResponse(consent_url)


@router.get("/callback")
async def callback(
    request: Request,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
    token_service: Annotated[
        OAuthTokenService, Depends(get_oauth_token_service)
    ] = None,
) -> JSONResponse:
    """Handle Google OAuth callback, exchange code, fetch channel id, store tokens."""
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or state"
        )

    _validate_state(state, settings.oauth_app_secret)

    token_payload = {
        "code": code,
        "client_id": settings.youtube_client_id,
        "client_secret": settings.youtube_client_secret,
        "redirect_uri": settings.youtube_redirect_uri,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token", data=token_payload
        )
        if token_resp.status_code != 200:
            logger.error(
                "Token exchange failed: %s %s", token_resp.status_code, token_resp.text
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code",
            )

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        scope = token_data.get("scope")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No access token returned"
        )

    # Fetch channel id
    async with httpx.AsyncClient(timeout=20.0) as client:
        channels_resp = await client.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "id", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if channels_resp.status_code != 200:
            logger.error(
                "Failed to fetch channel id: %s %s",
                channels_resp.status_code,
                channels_resp.text,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to fetch channel id",
            )
        payload = channels_resp.json()
        items = payload.get("items") or []
        if not items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No channel id found"
            )
        account_id = items[0].get("id")

    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        if expires_in
        else None
    )

    stored = await token_service.store_tokens(
        provider=YouTubeService.PROVIDER,
        account_id=account_id,
        access_token=access_token,
        refresh_token=refresh_token,
        scope=scope,
        expires_at=expires_at,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "connected",
            "account_id": stored.account_id,
            "scope": stored.scope,
            "expires_at": stored.expires_at.isoformat() if stored.expires_at else None,
        },
    )


@router.get("/account")
async def account_status(
    settings: Annotated[Settings, Depends(get_settings)],
    token_service: Annotated[OAuthTokenService, Depends(get_oauth_token_service)],
    account_id: Optional[str] = None,
) -> dict:
    """Report whether tokens exist for the given account (or any)."""
    token = await token_service.get_tokens(YouTubeService.PROVIDER, account_id)
    return {
        "connected": token is not None,
        "account_id": token.account_id if token else None,
        "scope": token.scope if token else None,
        "expires_at": (
            token.expires_at.isoformat() if token and token.expires_at else None
        ),
        "has_refresh_token": bool(token and token.refresh_token)
        or bool(settings.youtube_refresh_token),
    }
