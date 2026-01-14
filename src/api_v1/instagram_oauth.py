"""Instagram Business Login OAuth endpoints."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
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
from src.core.repositories.user_repository import UserRepository
from src.core.repositories.worker_app_repository import WorkerAppRepository
from src.core.services.oauth_token_service import OAuthTokenService
from src.core.services.security import create_internal_service_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/instagram", tags=["instagram-oauth"])

PROVIDER = "instagram"
STATE_TTL_SECONDS = 600
SHORT_TOKEN_URL = "https://api.instagram.com/oauth/access_token"
LONG_TOKEN_URL = "https://graph.instagram.com/access_token"
REFRESH_TOKEN_URL = "https://graph.instagram.com/refresh_access_token"


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


def _parse_scopes(raw: str | None) -> list[str]:
    if not raw:
        return [
            "instagram_business_basic",
            "instagram_business_content_publish",
            "instagram_business_manage_messages",
            "instagram_business_manage_comments",
        ]
    legacy_map = {
        "business_basic": "instagram_business_basic",
        "business_content_publish": "instagram_business_content_publish",
        "business_manage_messages": "instagram_business_manage_messages",
        "business_manage_comments": "instagram_business_manage_comments",
    }
    parts = [part.strip() for part in raw.replace(",", " ").split() if part.strip()]
    if not parts:
        return [
            "instagram_business_basic",
            "instagram_business_content_publish",
            "instagram_business_manage_messages",
            "instagram_business_manage_comments",
        ]
    normalized: list[str] = []
    for part in parts:
        mapped = legacy_map.get(part, part)
        if mapped != part:
            logger.warning(
                "Instagram scope '%s' is deprecated; use '%s' instead.",
                part,
                mapped,
            )
        normalized.append(mapped)
    seen: set[str] = set()
    deduped: list[str] = []
    for scope in normalized:
        if scope not in seen:
            seen.add(scope)
            deduped.append(scope)
    return deduped


def _parse_subscribed_fields(raw: str | None) -> str:
    if not raw:
        return "comments"
    parts = [part.strip() for part in raw.replace(",", " ").split() if part.strip()]
    if not parts:
        return "comments"
    seen: set[str] = set()
    deduped: list[str] = []
    for field in parts:
        if field not in seen:
            seen.add(field)
            deduped.append(field)
    return ",".join(deduped)


def _split_auth_url(auth_url: str) -> tuple[str, dict[str, str]]:
    parsed = urlparse(auth_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    base_url = urlunparse(parsed._replace(query=""))
    return base_url, query


def _resolve_instagram_oauth_config(
    settings: Settings,
) -> tuple[str, str, Optional[str], dict[str, str], str]:
    base_auth_url, auth_defaults = _split_auth_url(settings.instagram.auth_url)
    client_id = settings.instagram.app_id or auth_defaults.get("client_id")
    redirect_uri = settings.instagram.redirect_uri or auth_defaults.get("redirect_uri")
    scope_source = settings.instagram.auth_scopes or auth_defaults.get("scope")

    missing = []
    if not client_id:
        missing.append("INSTAGRAM_APP_ID")
    if not redirect_uri:
        missing.append("INSTAGRAM_REDIRECT_URI")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Missing Instagram OAuth settings: "
                f"{', '.join(missing)} (or provide client_id/redirect_uri in INSTAGRAM_AUTH_URL)"
            ),
        )
    return client_id, redirect_uri, scope_source, auth_defaults, base_auth_url


def _extract_short_token_payload(payload: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
    data = payload
    if isinstance(payload.get("data"), list) and payload["data"]:
        data = payload["data"][0] or {}

    access_token = data.get("access_token")
    user_id = data.get("user_id")
    permissions = data.get("permissions") or data.get("scope")
    if isinstance(permissions, list):
        permissions = ",".join([str(item) for item in permissions if item])
    return access_token, user_id, permissions


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
    force_reauth: Optional[bool] = Query(None),
) -> Response:
    """Build the Instagram consent URL and return it for frontend redirection."""
    client_id, redirect_uri, scope_source, auth_defaults, base_auth_url = (
        _resolve_instagram_oauth_config(settings)
    )
    if not current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User id missing"
        )

    state = _generate_state(settings.oauth_app_secret, str(current_user.id), redirect_to)
    scopes = _parse_scopes(scope_source)
    scope_value = ",".join(scopes)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope_value,
        "state": state,
    }
    if force_reauth is not None:
        params["force_reauth"] = "true" if force_reauth else "false"
    elif auth_defaults.get("force_reauth"):
        params["force_reauth"] = auth_defaults["force_reauth"]

    auth_url = _with_query(base_auth_url, params)

    if return_url:
        return JSONResponse({"auth_url": auth_url})
    return RedirectResponse(auth_url)


@router.get("/callback", response_class=Response, response_model=None)
async def callback(
    request: Request,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_reason: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
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
    """Handle Instagram OAuth callback, exchange code, and store long-lived token."""
    client_id, redirect_uri, scope_source, _, _ = _resolve_instagram_oauth_config(settings)

    if error:
        detail = error_description or error_reason or error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

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
        "client_id": client_id,
        "client_secret": settings.instagram.app_secret,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "code": code,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        token_resp = await client.post(SHORT_TOKEN_URL, data=token_payload)
        if token_resp.status_code != 200:
            logger.error(
                "Instagram token exchange failed: %s %s",
                token_resp.status_code,
                token_resp.text,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code",
            )
        token_data = token_resp.json()

    short_token, ig_user_id, permissions = _extract_short_token_payload(token_data)

    if not short_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No access token returned"
        )
    if not ig_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No Instagram user id returned"
        )

    exchange_params = {
        "grant_type": "ig_exchange_token",
        "client_secret": settings.instagram.app_secret,
        "access_token": short_token,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        exchange_resp = await client.get(LONG_TOKEN_URL, params=exchange_params)
        if exchange_resp.status_code != 200:
            logger.error(
                "Instagram long-lived exchange failed: %s %s",
                exchange_resp.status_code,
                exchange_resp.text,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange for long-lived token",
            )
        exchange_data = exchange_resp.json()

    long_token = exchange_data.get("access_token")
    expires_in = exchange_data.get("expires_in")
    token_type = exchange_data.get("token_type") or "bearer"

    if not long_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No long-lived access token returned",
        )

    access_expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        if expires_in
        else None
    )

    api_base_url = settings.instagram.api_base_url.rstrip("/")
    me_url = f"{api_base_url}/me"
    async with httpx.AsyncClient(timeout=20.0) as client:
        me_resp = await client.get(
            me_url,
            params={"fields": "user_id,username", "access_token": long_token},
        )
        if me_resp.status_code != 200:
            logger.error(
                "Instagram /me lookup failed: %s %s",
                me_resp.status_code,
                me_resp.text,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to fetch Instagram profile",
            )
        me_data = me_resp.json()

    account_id = me_data.get("user_id") or me_data.get("id")
    instagram_user_id = me_data.get("id") or ig_user_id
    username = me_data.get("username")
    if not account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instagram account id not returned",
        )

    if not permissions:
        permissions = ",".join(_parse_scopes(scope_source))

    subscription_success = False
    subscribed_fields = _parse_subscribed_fields(
        settings.instagram.webhook_subscribed_fields
    )
    subscribe_url = f"{api_base_url}/{account_id}/subscribed_apps"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            subscribe_resp = await client.post(
                subscribe_url,
                params={
                    "subscribed_fields": subscribed_fields,
                    "access_token": long_token,
                },
            )
            if subscribe_resp.status_code == 200:
                try:
                    subscribe_data = subscribe_resp.json()
                except ValueError:
                    subscribe_data = {}
                subscription_success = bool(subscribe_data.get("success"))
                if not subscription_success:
                    logger.error(
                        "Instagram subscription failed: %s %s",
                        subscribe_resp.status_code,
                        subscribe_resp.text,
                    )
            else:
                logger.error(
                    "Instagram subscription failed: %s %s",
                    subscribe_resp.status_code,
                    subscribe_resp.text,
                )
    except Exception as exc:
        logger.error("Instagram subscription request failed: %s", exc)

    # Encrypt tokens for worker backend
    fernet = Fernet(settings.oauth_encryption_key)
    try:
        access_token_encrypted = fernet.encrypt(long_token.encode("utf-8")).decode(
            "utf-8"
        )
    except Exception as exc:
        logger.error("Failed to encrypt tokens for worker backend: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to encrypt tokens",
        )

    stored = await token_service.store_tokens(
        provider=PROVIDER,
        account_id=str(account_id),
        user_id=user.id,
        instagram_user_id=str(instagram_user_id) if instagram_user_id else None,
        username=username,
        access_token=long_token,
        refresh_token=None,
        scope=permissions,
        access_token_expires_at=access_expires_at,
        refresh_token_expires_at=None,
    )
    await session.commit()

    worker_synced = False
    worker_app = await worker_app_repo.get_by_user_id(user.id)
    if worker_app:
        base_target = worker_app.webhook_url or worker_app.base_url
        parsed = urlparse(base_target)
        if parsed.scheme and parsed.netloc:
            worker_endpoint = f"{parsed.scheme}://{parsed.netloc}/api/v1/oauth/tokens"
            payload = {
                "provider": PROVIDER,
                "account_id": stored.account_id,
                "instagram_user_id": stored.instagram_user_id,
                "username": stored.username,
                "access_token_encrypted": access_token_encrypted,
                "token_type": token_type,
                "scope": permissions,
            }
            if access_expires_at:
                payload["access_token_expires_at"] = access_expires_at.isoformat()
            if expires_in:
                payload["access_token_expires_in"] = expires_in

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
        or "https://lunitunestmb.com/chatico/settings"
    )
    if redirect_target:
        try:
            redirect_url = _with_query(
                redirect_target,
                {
                    "instagram_status": "connected",
                    "instagram_worker_synced": str(worker_synced).lower(),
                    "instagram_subscription_success": str(subscription_success).lower(),
                    "instagram_access_expires_at": stored.access_token_expires_at.isoformat()
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
            "subscription_success": subscription_success,
            "access_token_expires_at": stored.access_token_expires_at.isoformat()
            if stored.access_token_expires_at
            else None,
            "access_token_expires_in": expires_in,
            "expires_at": stored.access_token_expires_at.isoformat()
            if stored.access_token_expires_at
            else None,
            "worker_synced": worker_synced,
        },
    )


@router.post("/refresh")
async def refresh_token(
    current_user: Annotated[User, Depends(get_current_active_user)],
    token_service: Annotated[OAuthTokenService, Depends(get_oauth_token_service)],
    worker_app_repo: Annotated[
        WorkerAppRepository, Depends(get_worker_app_repository)
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    account_id: Optional[str] = None,
) -> dict:
    """
    Refresh a long-lived Instagram access token and persist the new value.
    """
    token = await token_service.get_tokens(
        PROVIDER, user_id=current_user.id, account_id=account_id
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No Instagram tokens found"
        )

    refresh_params = {
        "grant_type": "ig_refresh_token",
        "access_token": token.access_token,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        refresh_resp = await client.get(REFRESH_TOKEN_URL, params=refresh_params)
        if refresh_resp.status_code != 200:
            logger.error(
                "Instagram refresh failed: %s %s",
                refresh_resp.status_code,
                refresh_resp.text,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to refresh Instagram token",
            )
        refresh_data = refresh_resp.json()

    new_token = refresh_data.get("access_token")
    expires_in = refresh_data.get("expires_in")
    token_type = refresh_data.get("token_type") or "bearer"

    if not new_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No refreshed access token returned",
        )

    access_expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        if expires_in
        else None
    )

    updated = await token_service.update_access_token(
        provider=PROVIDER,
        account_id=token.account_id,
        user_id=current_user.id,
        access_token=new_token,
        refresh_token=None,
        access_token_expires_at=access_expires_at,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Instagram tokens found",
        )
    await session.commit()

    worker_synced = False
    worker_app = await worker_app_repo.get_by_user_id(current_user.id)
    if worker_app:
        base_target = worker_app.webhook_url or worker_app.base_url
        parsed = urlparse(base_target)
        if parsed.scheme and parsed.netloc:
            worker_endpoint = f"{parsed.scheme}://{parsed.netloc}/api/v1/oauth/tokens"
            fernet = Fernet(settings.oauth_encryption_key)
            try:
                access_token_encrypted = fernet.encrypt(new_token.encode("utf-8")).decode(
                    "utf-8"
                )
            except Exception as exc:
                logger.error("Failed to encrypt tokens for worker backend: %s", exc)
                access_token_encrypted = None

            if access_token_encrypted:
                payload = {
                    "provider": PROVIDER,
                    "account_id": token.account_id,
                    "instagram_user_id": updated.instagram_user_id,
                    "username": updated.username,
                    "access_token_encrypted": access_token_encrypted,
                    "token_type": token_type,
                    "scope": token.scope,
                }
                if access_expires_at:
                    payload["access_token_expires_at"] = access_expires_at.isoformat()
                if expires_in:
                    payload["access_token_expires_in"] = expires_in

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
                            "Worker backend rejected refreshed tokens: status=%s body=%s endpoint=%s",
                            worker_resp.status_code,
                            worker_resp.text,
                            worker_endpoint,
                        )
                    else:
                        worker_synced = True
                except Exception as exc:
                    logger.error("Failed to send refreshed tokens to worker backend: %s", exc)
        else:
            logger.error("Worker app URL is invalid: %s", base_target)
    else:
        logger.info("Worker app not configured; skipping worker token refresh sync.")

    return {
        "status": "refreshed",
        "account_id": token.account_id,
        "access_token_expires_at": access_expires_at.isoformat()
        if access_expires_at
        else None,
        "access_token_expires_in": expires_in,
        "worker_synced": worker_synced,
    }


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
    Remove Instagram credentials for the current user and notify worker backend.
    """
    token = await token_service.get_tokens(
        PROVIDER, user_id=current_user.id, account_id=account_id
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No Instagram tokens found"
        )

    account_id = token.account_id
    deleted = await token_service.delete_tokens(
        provider=PROVIDER, user_id=current_user.id, account_id=account_id
    )
    await session.commit()

    worker_synced = False
    worker_app = await worker_app_repo.get_by_user_id(current_user.id)
    if worker_app:
        base_target = worker_app.webhook_url or worker_app.base_url
        parsed = urlparse(base_target)
        if parsed.scheme and parsed.netloc:
            worker_endpoint = f"{parsed.scheme}://{parsed.netloc}/api/v1/oauth/tokens"
            payload = {"provider": PROVIDER, "account_id": account_id}
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
    """Report whether Instagram tokens exist for the given account (or any)."""
    token = await token_service.get_tokens(
        PROVIDER, user_id=current_user.id, account_id=account_id
    )
    access_expires_at = token.access_token_expires_at if token else None
    if access_expires_at and access_expires_at.tzinfo is None:
        access_expires_at = access_expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    access_token_valid = bool(access_expires_at is None or access_expires_at > now)
    connected = bool(token) and access_token_valid
    return {
        "connected": connected,
        "account_id": token.account_id if token else None,
        "scope": token.scope if token else None,
        "access_token_expires_at": (
            access_expires_at.isoformat()
            if access_expires_at
            else None
        ),
        "expires_at": (
            access_expires_at.isoformat()
            if access_expires_at
            else None
        ),
        "access_token_valid": access_token_valid,
    }
