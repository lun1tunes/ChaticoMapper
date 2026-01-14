from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from src.api_v1.instagram_oauth import _generate_state, _validate_state
from src.core.config import get_settings
from src.core.dependencies import get_current_active_user
from src.core.dependencies import get_user_repository, get_worker_app_repository
from src.core.models.user import User
from src.core.repositories.oauth_token_repository import OAuthTokenRepository
from src.core.services.oauth_token_service import OAuthTokenService
from src.main import app


class DummyResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or ""

    def json(self):
        return self._json


async def _create_user(db_session) -> User:
    user = User(
        username=f"ig-oauth-{uuid4()}",
        full_name="Instagram OAuth User",
        hashed_password="hashed-password",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _store_token(
    session,
    user: User,
    *,
    account_id: str,
    expires_delta: timedelta | None,
) -> datetime | None:
    service = OAuthTokenService(
        OAuthTokenRepository(session),
        get_settings().oauth_encryption_key,
    )
    access_expires_at = (
        datetime.now(timezone.utc) + expires_delta if expires_delta is not None else None
    )

    await service.store_tokens(
        provider="instagram",
        account_id=account_id,
        user_id=user.id,
        access_token=f"access-{account_id}",
        refresh_token=None,
        scope="instagram_business_basic",
        access_token_expires_at=access_expires_at,
        refresh_token_expires_at=None,
    )
    await session.commit()
    return access_expires_at


@contextmanager
def _override_active_user(user: User):
    async def _override():
        return user

    app.dependency_overrides[get_current_active_user] = _override
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


@contextmanager
def _override_user_and_worker(user: User, worker_app=None):
    class _StubUserRepo:
        async def get_by_id(self, user_id):
            return user

    class _StubWorkerRepo:
        async def get_by_user_id(self, user_id):
            return worker_app

    app.dependency_overrides[get_user_repository] = lambda: _StubUserRepo()
    app.dependency_overrides[get_worker_app_repository] = lambda: _StubWorkerRepo()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_user_repository, None)
        app.dependency_overrides.pop(get_worker_app_repository, None)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_authorize_returns_consent_url_json(client, db_session):
    user = await _create_user(db_session)
    settings = get_settings()

    with _override_active_user(user):
        response = await client.get(
            "/api/v1/auth/instagram/authorize",
            params={"redirect_to": "https://example.com/after"},
        )

    assert response.status_code == 200
    payload = response.json()
    auth_url = payload["auth_url"]
    assert auth_url.startswith("https://www.instagram.com/oauth/authorize?")
    parsed = urlparse(auth_url)
    params = parse_qs(parsed.query)
    assert params["client_id"][0] == settings.instagram.app_id
    assert params["redirect_uri"][0] == settings.instagram.redirect_uri
    assert params["response_type"][0] == "code"
    assert "state" in params and params["state"][0]
    scopes = set(params["scope"][0].split(","))
    assert "instagram_business_basic" in scopes
    assert "instagram_business_manage_comments" in scopes
    _, redirect = _validate_state(params["state"][0], settings.oauth_app_secret)
    assert redirect == "https://example.com/after"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_account_status_reports_disconnected_without_tokens(client, db_session):
    user = await _create_user(db_session)

    with _override_active_user(user):
        response = await client.get("/api/v1/auth/instagram/account")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is False
    assert payload["account_id"] is None
    assert payload["access_token_valid"] is True


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_callback_exchanges_tokens_and_syncs_worker(client, db_session, monkeypatch):
    settings = get_settings()
    user = await _create_user(db_session)

    from src.core.models.worker_app import WorkerApp

    worker_app = WorkerApp(
        base_url="https://worker.example/api",
        webhook_url="https://worker.example/hook",
        user_id=user.id,
    )
    db_session.add(worker_app)
    await db_session.commit()

    class DummyClient:
        def __init__(self, *args, **kwargs):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, json=None, headers=None, **kwargs):
            self.calls.append(("post", url))
            if "api.instagram.com/oauth/access_token" in url:
                return DummyResponse(
                    200,
                    {
                        "access_token": "short-token",
                        "user_id": "ig-scoped-123",
                        "permissions": "instagram_business_basic,instagram_business_manage_comments",
                    },
                )
            if "api/v1/oauth/tokens" in url:
                return DummyResponse(200, {})
            return DummyResponse(500, {}, "unexpected post")

        async def get(self, url, params=None, headers=None, **kwargs):
            self.calls.append(("get", url))
            if "graph.instagram.com/access_token" in url:
                return DummyResponse(
                    200,
                    {"access_token": "long-token", "expires_in": 3600, "token_type": "bearer"},
                )
            if url.endswith("/me"):
                return DummyResponse(
                    200,
                    {
                        "user_id": "ig-account-456",
                        "username": "owner-ig",
                        "id": "ig-scoped-123",
                    },
                )
            return DummyResponse(404, {}, "not found")

    monkeypatch.setattr("src.api_v1.instagram_oauth.httpx.AsyncClient", DummyClient)

    state = _generate_state(
        settings.oauth_app_secret,
        str(user.id),
        redirect_to="https://frontend.example/settings",
    )
    with _override_user_and_worker(user, worker_app):
        response = await client.get(
            "/api/v1/auth/instagram/callback",
            params={"code": "dummy-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code in {302, 303, 307}
    redirected = response.headers["location"]
    parsed = urlparse(redirected)
    query = parse_qs(parsed.query)
    assert query["instagram_status"][0] == "connected"
    assert query["instagram_worker_synced"][0] == "true"
    assert query["instagram_access_expires_at"][0]

    stored = await OAuthTokenService(
        OAuthTokenRepository(db_session), settings.oauth_encryption_key
    ).get_tokens("instagram", user_id=user.id)
    assert stored is not None
    assert stored.account_id == "ig-account-456"
    assert stored.instagram_user_id == "ig-scoped-123"
    assert stored.username == "owner-ig"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_refresh_updates_token_and_returns_status(client, db_session, monkeypatch):
    settings = get_settings()
    user = await _create_user(db_session)
    await _store_token(db_session, user, account_id="ig-refresh", expires_delta=timedelta(hours=1))

    class RefreshClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None, headers=None, **kwargs):
            return DummyResponse(
                200,
                {"access_token": "new-token", "expires_in": 7200, "token_type": "bearer"},
            )

        async def post(self, url, json=None, headers=None, **kwargs):
            return DummyResponse(200, {})

    monkeypatch.setattr("src.api_v1.instagram_oauth.httpx.AsyncClient", RefreshClient)

    with _override_active_user(user):
        response = await client.post("/api/v1/auth/instagram/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "refreshed"
    assert payload["access_token_expires_in"] == 7200

    stored = await OAuthTokenService(
        OAuthTokenRepository(db_session), settings.oauth_encryption_key
    ).get_tokens("instagram", user_id=user.id)
    assert stored is not None
    assert stored.access_token == "new-token"
