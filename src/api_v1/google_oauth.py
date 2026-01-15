"""Google/YouTube OAuth endpoints."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from typing import Annotated, Optional
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings, get_settings
from src.core.dependencies import (
    get_current_active_user,
    get_oauth_token_service,
    get_session,
    get_user_repository,
    get_worker_app_repository,
)
from src.core.models.user import User
from src.core.repositories.worker_app_repository import WorkerAppRepository
from src.core.repositories.user_repository import UserRepository
from src.core.services.oauth_token_service import OAuthTokenService
from src.core.services.security import create_internal_service_token
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


def _generate_state(app_secret: str, user_id: str, redirect_to: Optional[str] = None) -> str:
    nonce = str(uuid4())
    expires_at = int(time.time()) + STATE_TTL_SECONDS
    redirect_b64 = (
        base64.urlsafe_b64encode(redirect_to.encode("utf-8")).decode("utf-8").rstrip("=")
        if redirect_to
        else ""
    )
    payload = f"{nonce}:{expires_at}:{user_id}:{redirect_b64}"
    signature = _sign_state(payload, app_secret)
    return f"{payload}:{signature}"


def _validate_state(state: str, app_secret: str) -> tuple[str, Optional[str]]:
    parts = state.split(":")
    if len(parts) == 5:
        nonce, exp_str, user_id, redirect_b64, signature = parts
        payload = f"{nonce}:{exp_str}:{user_id}:{redirect_b64}"
    elif len(parts) == 4:
        nonce, exp_str, user_id, signature = parts
        redirect_b64 = ""
        payload = f"{nonce}:{exp_str}:{user_id}"
    else:
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

    redirect_to: Optional[str] = None
    if redirect_b64:
        padded = redirect_b64 + "=" * (-len(redirect_b64) % 4)
        try:
            redirect_to = base64.urlsafe_b64decode(padded).decode("utf-8")
        except Exception:
            redirect_to = None

    return user_id, redirect_to


def _with_query(url: str, extra: dict[str, str]) -> str:
    parsed = urlparse(url)
    current_qs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current_qs.update(extra)
    new_query = urlencode(current_qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _resolve_default_redirect(settings: Settings, redirect_uri: str) -> Optional[str]:
    if settings.oauth_redirect_url:
        return settings.oauth_redirect_url
    if not redirect_uri:
        return None
    parsed = urlparse(redirect_uri)
    if not parsed.scheme or not parsed.netloc:
        return None
    path = settings.oauth_redirect_path or "/chatico/settings"
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"


@router.get("/authorize", response_class=Response, response_model=None)
async def authorize(
    request: Request,
    current_user: Annotated[User, Depends(get_current_active_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    redirect_to: Optional[str] = Query(default=None),
    return_url: bool = Query(
        True,
        description=(
            "Return JSON with consent URL instead of redirect. "
            "Default True to avoid browser following redirects in XHR."
        ),
    ),
) -> Response:
    """Build the Google consent screen URL and redirect the user."""
    if not current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User id missing"
        )

    state = _generate_state(settings.oauth_app_secret, str(current_user.id), redirect_to)

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

    # Always return JSON when return_url is truthy (default True) to prevent CORS issues in XHR.
    if return_url:
        return JSONResponse({"auth_url": consent_url})

    # Fallback: direct redirect
    return RedirectResponse(consent_url)


@router.get("/callback", response_class=Response, response_model=None)
async def callback(
    request: Request,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
    user_repo: Annotated[UserRepository, Depends(get_user_repository)] = None,
    worker_app_repo: Annotated[
        WorkerAppRepository, Depends(get_worker_app_repository)
    ] = None,
    token_service: Annotated[
        OAuthTokenService, Depends(get_oauth_token_service)
    ] = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
) -> Response:
    """Handle Google OAuth callback, exchange code, fetch channel id, store tokens."""
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or state"
        )

    user_id, redirect_from_state = _validate_state(state, settings.oauth_app_secret)

    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User referenced in state not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User is inactive"
        )

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
        refresh_token_expires_in = token_data.get("refresh_token_expires_in")
        scope = token_data.get("scope")

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No access token returned"
        )
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No refresh token returned"
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
    refresh_token_expires_at = None
    if refresh_token_expires_in:
        try:
            refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=int(refresh_token_expires_in)
            )
        except (TypeError, ValueError):
            refresh_token_expires_at = None

    # Encrypt tokens for worker backend
    fernet = Fernet(settings.oauth_encryption_key)
    try:
        access_token_encrypted = fernet.encrypt(access_token.encode("utf-8")).decode(
            "utf-8"
        )
        refresh_token_encrypted = (
            fernet.encrypt(refresh_token.encode("utf-8")).decode("utf-8")
            if refresh_token
            else None
        )
    except Exception as exc:
        logger.error("Failed to encrypt tokens for worker backend: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to encrypt tokens",
        )

    stored = await token_service.store_tokens(
        provider=YouTubeService.PROVIDER,
        account_id=account_id,
        user_id=user.id,
        access_token=access_token,
        refresh_token=refresh_token,
        scope=scope,
        access_token_expires_at=expires_at,
        refresh_token_expires_at=refresh_token_expires_at,
    )
    await session.commit()

    worker_synced = False
    worker_app = await worker_app_repo.get_by_user_id(user.id)
    if worker_app:
        # Use the same host/port as webhook forwarding; swap the route to oauth tokens
        base_target = worker_app.webhook_url or worker_app.base_url
        parsed = urlparse(base_target)
        if parsed.scheme and parsed.netloc:
            worker_endpoint = f"{parsed.scheme}://{parsed.netloc}/api/v1/oauth/tokens"
            payload = {
                "provider": YouTubeService.PROVIDER,
                "account_id": account_id,
                "access_token_encrypted": access_token_encrypted,
                "refresh_token_encrypted": refresh_token_encrypted,
                "token_type": "Bearer",
                "scope": scope,
            }
            if expires_at:
                payload["access_token_expires_at"] = expires_at.isoformat()
            if expires_in:
                payload["access_token_expires_in"] = expires_in
            if refresh_token_expires_at:
                payload["refresh_token_expires_at"] = refresh_token_expires_at.isoformat()
            if refresh_token_expires_in:
                payload["refresh_token_expires_in"] = refresh_token_expires_in

            try:
                internal_jwt = create_internal_service_token()
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {internal_jwt}",
                }
                async with httpx.AsyncClient(timeout=20.0) as client:
                    worker_resp = await client.post(
                        worker_endpoint,
                        json=payload,
                        headers=headers,
                    )
                if worker_resp.status_code >= 400:
                    logger.error(
                        "Worker backend rejected tokens: status=%s body=%s endpoint=%s",
                        worker_resp.status_code,
                        worker_resp.text,
                        worker_endpoint,
                    )
                else:
                    worker_synced = True
            except Exception as exc:
                logger.error("Failed to send tokens to worker backend: %s", exc)
        else:
            logger.error("Worker app URL is invalid: %s", base_target)
    else:
        logger.warning("Worker app is not configured for user_id=%s; skipping worker sync", user.id)

    redirect_target = (
        redirect_from_state
        or request.query_params.get("redirect_to")
        or _resolve_default_redirect(settings, settings.youtube_redirect_uri)
    )
    # Append status info for the frontend to consume
    if redirect_target:
        try:
            redirect_url = _with_query(
                redirect_target,
                {
                    "youtube_status": "connected",
                    "youtube_worker_synced": str(worker_synced).lower(),
                    "youtube_access_expires_at": stored.access_token_expires_at.isoformat()
                    if stored.access_token_expires_at
                    else "",
                },
            )
            return RedirectResponse(redirect_url)
        except Exception as exc:
            logger.warning("Failed to build redirect url %s: %s", redirect_target, exc)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "connected",
            "account_id": stored.account_id,
            "scope": stored.scope,
            # Explicitly surface which token expiry this is (access token)
            "access_token_expires_at": stored.access_token_expires_at.isoformat()
            if stored.access_token_expires_at
            else None,
            "access_token_expires_in": expires_in,
            # Refresh tokens are long-lived; no expiry unless Google returns one (rare)
            "refresh_token_expires_at": stored.refresh_token_expires_at.isoformat()
            if stored.refresh_token_expires_at
            else None,
            # Legacy aliases for backward compatibility
            "expires_at": stored.access_token_expires_at.isoformat()
            if stored.access_token_expires_at
            else None,
            "expires_in": expires_in,
            "worker_synced": worker_synced,
        },
    )


@router.delete("/account")
async def disconnect_account(
    current_user: Annotated[User, Depends(get_current_active_user)],
    token_service: Annotated[OAuthTokenService, Depends(get_oauth_token_service)],
    worker_app_repo: Annotated[
        WorkerAppRepository, Depends(get_worker_app_repository)
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    account_id: Optional[str] = None,
) -> dict:
    """
    Remove YouTube credentials for the current user and notify worker backend.
    """
    token = await token_service.get_tokens(
        YouTubeService.PROVIDER, user_id=current_user.id, account_id=account_id
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No YouTube tokens found"
        )

    account_id = token.account_id
    deleted = await token_service.delete_tokens(
        provider=YouTubeService.PROVIDER, user_id=current_user.id, account_id=account_id
    )
    await session.commit()

    worker_synced = False
    worker_app = await worker_app_repo.get_by_user_id(current_user.id)
    if worker_app:
        base_target = worker_app.webhook_url or worker_app.base_url
        parsed = urlparse(base_target)
        if parsed.scheme and parsed.netloc:
            worker_endpoint = f"{parsed.scheme}://{parsed.netloc}/api/v1/oauth/tokens"
            payload = {"provider": YouTubeService.PROVIDER, "account_id": account_id}
            try:
                internal_jwt = create_internal_service_token()
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {internal_jwt}",
                }
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.delete(worker_endpoint, json=payload, headers=headers)
                if resp.status_code < 400:
                    worker_synced = True
                else:
                    logger.error(
                        "Worker backend rejected delete: status=%s body=%s endpoint=%s",
                        resp.status_code,
                        resp.text,
                        worker_endpoint,
                    )
            except Exception as exc:  # pragma: no cover - network guard rail
                logger.error("Failed to notify worker backend about disconnect: %s", exc)
        else:
            logger.error("Worker app URL is invalid: %s", base_target)
    else:
        logger.info("Worker app not configured; skipping worker token revoke.")

    return {
        "status": "disconnected" if deleted else "not_found",
        "account_id": account_id,
        "worker_synced": worker_synced,
    }


@router.get("/account")
async def account_status(
    current_user: Annotated[User, Depends(get_current_active_user)],
    token_service: Annotated[OAuthTokenService, Depends(get_oauth_token_service)],
    account_id: Optional[str] = None,
) -> dict:
    """Report whether tokens exist for the given account (or any)."""
    token = await token_service.get_tokens(
        YouTubeService.PROVIDER, user_id=current_user.id, account_id=account_id
    )
    access_expires_at = token.access_token_expires_at if token else None
    refresh_expires_at = token.refresh_token_expires_at if token else None
    # Normalize to aware UTC for comparison
    if access_expires_at and access_expires_at.tzinfo is None:
        access_expires_at = access_expires_at.replace(tzinfo=timezone.utc)
    if refresh_expires_at and refresh_expires_at.tzinfo is None:
        refresh_expires_at = refresh_expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    access_token_valid = bool(access_expires_at is None or access_expires_at > now)
    refresh_token_valid = bool(
        token
        and token.refresh_token
        and (refresh_expires_at is None or refresh_expires_at > now)
    )
    connected = bool(token) and (access_token_valid or refresh_token_valid)
    return {
        # Connected when at least one credential (access/refresh) is still valid
        "connected": connected,
        "account_id": token.account_id if token else None,
        "scope": token.scope if token else None,
        "access_token_expires_at": (
            access_expires_at.isoformat()
            if access_expires_at
            else None
        ),
        "refresh_token_expires_at": (
            refresh_expires_at.isoformat()
            if refresh_expires_at
            else None
        ),
        # Legacy alias (access token expiry)
        "expires_at": (
            access_expires_at.isoformat()
            if access_expires_at
            else None
        ),
        "has_refresh_token": bool(token and token.refresh_token),
        "access_token_valid": access_token_valid,
        "refresh_token_valid": refresh_token_valid,
        # Signal that we can refresh immediately without re-consent
        "needs_refresh": bool(token) and refresh_token_valid and not access_token_valid,
    }
