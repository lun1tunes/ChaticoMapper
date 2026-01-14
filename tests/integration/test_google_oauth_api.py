from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from src.core.config import get_settings
from src.core.dependencies import get_current_active_user
from src.core.models.user import User
from src.core.repositories.oauth_token_repository import OAuthTokenRepository
from src.core.services.oauth_token_service import OAuthTokenService
from src.core.services.youtube_service import YouTubeService
from src.main import app
from src.api_v1.google_oauth import _generate_state
from src.core.dependencies import get_user_repository, get_worker_app_repository


class DummyResponse:
    def __init__(self, status_code: int, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or ""

    def json(self):
        return self._json


async def _create_user(db_session) -> User:
    user = User(
        username=f"oauth-api-{uuid4()}",
        full_name="OAuth API User",
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
    refresh_expires_delta: timedelta | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Persist an OAuth token using the real service to exercise encryption/decryption."""
    service = OAuthTokenService(
        OAuthTokenRepository(session),
        get_settings().oauth_encryption_key,
    )
    access_expires_at = (
        datetime.now(timezone.utc) + expires_delta if expires_delta is not None else None
    )
    refresh_expires_at = (
        datetime.now(timezone.utc) + refresh_expires_delta
        if refresh_expires_delta is not None
        else None
    )

    await service.store_tokens(
        provider=YouTubeService.PROVIDER,
        account_id=account_id,
        user_id=user.id,
        access_token=f"access-{account_id}",
        refresh_token=f"refresh-{account_id}",
        scope="https://www.googleapis.com/auth/youtube.force-ssl",
        access_token_expires_at=access_expires_at,
        refresh_token_expires_at=refresh_expires_at,
    )
    await session.commit()
    return access_expires_at, refresh_expires_at


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
async def test_account_status_reports_disconnected_without_tokens(client, db_session):
    user = await _create_user(db_session)

    with _override_active_user(user):
        response = await client.get("/api/v1/auth/google/account")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is False
    assert payload["account_id"] is None
    assert payload["has_refresh_token"] is False
    assert payload["access_token_expires_at"] is None
    # When no token exists the API still reports validity as true (nothing to expire)
    assert payload["access_token_valid"] is True


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_account_status_connected_when_token_is_valid(client, db_session):
    user = await _create_user(db_session)
    access_expires_at, refresh_expires_at = await _store_token(
        db_session,
        user,
        account_id="channel-valid",
        expires_delta=timedelta(hours=2),
        refresh_expires_delta=timedelta(days=30),
    )

    with _override_active_user(user):
        response = await client.get("/api/v1/auth/google/account")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is True
    assert payload["account_id"] == "channel-valid"
    assert payload["has_refresh_token"] is True
    assert payload["access_token_valid"] is True
    assert payload["access_token_expires_at"] == access_expires_at.isoformat()
    assert payload["expires_at"] == access_expires_at.isoformat()
    assert payload["refresh_token_expires_at"] == refresh_expires_at.isoformat()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_account_status_marks_expired_token_as_disconnected(client, db_session):
    user = await _create_user(db_session)
    access_expires_at, _ = await _store_token(
        db_session,
        user,
        account_id="channel-expired",
        expires_delta=timedelta(minutes=-5),
        refresh_expires_delta=timedelta(minutes=-5),
    )

    with _override_active_user(user):
        response = await client.get("/api/v1/auth/google/account")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connected"] is False
    assert payload["access_token_valid"] is False
    assert payload["refresh_token_valid"] is False
    assert payload["access_token_expires_at"] == access_expires_at.isoformat()
    assert payload["expires_at"] == access_expires_at.isoformat()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_account_status_filters_by_account_id(client, db_session):
    user = await _create_user(db_session)
    # Seed multiple accounts to ensure the query parameter targets the requested one.
    await _store_token(
        db_session,
        user,
        account_id="channel-old",
        expires_delta=timedelta(hours=-1),
    )
    await _store_token(
        db_session,
        user,
        account_id="channel-target",
        expires_delta=timedelta(minutes=30),
    )

    with _override_active_user(user):
        response = await client.get(
            "/api/v1/auth/google/account",
            params={"account_id": "channel-target"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["account_id"] == "channel-target"
    assert payload["connected"] is True
    assert payload["access_token_valid"] is True


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_authorize_returns_consent_url_json(client, db_session):
    user = await _create_user(db_session)

    with _override_active_user(user):
        response = await client.get(
            "/api/v1/auth/google/authorize",
            params={"redirect_to": "https://example.com/after"},
        )

    assert response.status_code == 200
    payload = response.json()
    auth_url = payload["auth_url"]
    assert auth_url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    parsed = urlparse(auth_url)
    params = parse_qs(parsed.query)
    # The URL should include key parameters for offline access
    assert params["client_id"][0] == get_settings().youtube_client_id
    assert params["redirect_uri"][0] == get_settings().youtube_redirect_uri
    assert params["access_type"][0] == "offline"
    assert params["include_granted_scopes"][0] == "true"
    assert "state" in params and params["state"][0]
    assert params["redirect_to"][0] == "https://example.com/after"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_authorize_can_redirect_when_requested(client, db_session):
    user = await _create_user(db_session)

    with _override_active_user(user):
        response = await client.get(
            "/api/v1/auth/google/authorize",
            params={"return_url": "false"},
            follow_redirects=False,
        )

    assert response.status_code in {302, 303, 307}
    location = response.headers.get("location")
    assert location and location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_callback_exchanges_tokens_and_syncs_worker(client, db_session, monkeypatch):
    settings = get_settings()
    user = await _create_user(db_session)

    # Create worker app to exercise sync flow
    worker_repo = OAuthTokenRepository(db_session)
    from src.core.repositories.worker_app_repository import WorkerAppRepository
    from src.core.models.worker_app import WorkerApp

    worker_app_repo = WorkerAppRepository(db_session)
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
            if "oauth2.googleapis.com/token" in url:
                return DummyResponse(
                    200,
                    {
                        "access_token": "token-123",
                        "refresh_token": "refresh-123",
                        "expires_in": 3600,
                        "refresh_token_expires_in": 86400,
                        "scope": "scope1 scope2",
                    },
                )
            if "api/v1/oauth/tokens" in url:
                return DummyResponse(200, {})
            return DummyResponse(500, {}, "unexpected post")

        async def get(self, url, params=None, headers=None, **kwargs):
            self.calls.append(("get", url))
            if "youtube/v3/channels" in url:
                return DummyResponse(200, {"items": [{"id": "channel-xyz"}]})
            return DummyResponse(404, {}, "not found")

    monkeypatch.setattr("src.api_v1.google_oauth.httpx.AsyncClient", DummyClient)

    state = _generate_state(settings.oauth_app_secret, str(user.id), redirect_to="https://frontend.example/settings")
    with _override_user_and_worker(user, worker_app):
        response = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "dummy-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code in {302, 303, 307}
    redirected = response.headers["location"]
    parsed = urlparse(redirected)
    query = parse_qs(parsed.query)
    assert query["youtube_status"][0] == "connected"
    assert query["youtube_worker_synced"][0] == "true"
    assert query["youtube_access_expires_at"][0]

    # Token persisted with expected account id
    stored = await OAuthTokenService(worker_repo, settings.oauth_encryption_key).get_tokens(
        YouTubeService.PROVIDER, user_id=user.id
    )
    assert stored is not None
    assert stored.account_id == "channel-xyz"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_callback_handles_token_exchange_failure(client, db_session, monkeypatch):
    settings = get_settings()
    user = await _create_user(db_session)

    class DummyResponse:
        def __init__(self, status_code: int, text: str = ""):
            self.status_code = status_code
            self.text = text

        def json(self):
            return {}

    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *args, **kwargs):
            return DummyResponse(400, "bad request")

        async def get(self, url, *args, **kwargs):
            return DummyResponse(400, "bad request")

    monkeypatch.setattr("src.api_v1.google_oauth.httpx.AsyncClient", FailingClient)

    state = _generate_state(settings.oauth_app_secret, str(user.id))
    with _override_user_and_worker(user, None):
        response = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Failed to exchange code"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_callback_requires_code_and_state(client):
    response = await client.get("/api/v1/auth/google/callback")
    assert response.status_code == 400
    assert response.json()["detail"] == "Missing code or state"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_callback_rejects_missing_refresh_token(client, db_session, monkeypatch):
    settings = get_settings()
    user = await _create_user(db_session)

    class NoRefreshClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *args, **kwargs):
            return DummyResponse(200, {"access_token": "only-access", "expires_in": 3600})

        async def get(self, url, *args, **kwargs):
            return DummyResponse(200, {"items": [{"id": "channel-none"}]})

    monkeypatch.setattr("src.api_v1.google_oauth.httpx.AsyncClient", NoRefreshClient)
    state = _generate_state(settings.oauth_app_secret, str(user.id))
    with _override_user_and_worker(user, None):
        response = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "No refresh token returned"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_callback_channel_lookup_failure(client, db_session, monkeypatch):
    settings = get_settings()
    user = await _create_user(db_session)

    class ChannelFailClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *args, **kwargs):
            return DummyResponse(200, {"access_token": "tok", "refresh_token": "ref", "expires_in": 3600})

        async def get(self, url, *args, **kwargs):
            return DummyResponse(400, text="fail")

    monkeypatch.setattr("src.api_v1.google_oauth.httpx.AsyncClient", ChannelFailClient)
    state = _generate_state(settings.oauth_app_secret, str(user.id))
    with _override_user_and_worker(user, None):
        response = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Failed to fetch channel id"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_callback_json_fallback_when_redirect_build_fails(client, db_session, monkeypatch):
    settings = get_settings()
    user = await _create_user(db_session)

    class WorkerErrorClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *args, **kwargs):
            if "oauth2.googleapis.com" in url:
                return DummyResponse(
                    200,
                    {
                        "access_token": "tok",
                        "refresh_token": "ref",
                        "expires_in": 3600,
                        "scope": "scope1",
                    },
                )
            # Worker sync failure path
            return DummyResponse(500, text="boom")

        async def get(self, url, *args, **kwargs):
            return DummyResponse(200, {"items": [{"id": "channel-json"}]})

    # Force _with_query to raise so we exercise JSON response path
    monkeypatch.setattr("src.api_v1.google_oauth.httpx.AsyncClient", WorkerErrorClient)
    monkeypatch.setattr("src.api_v1.google_oauth._with_query", lambda url, extra: (_ for _ in ()).throw(ValueError("bad url")))

    state = _generate_state(settings.oauth_app_secret, str(user.id))
    with _override_user_and_worker(user, None):
        response = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "connected"
    assert payload["account_id"] == "channel-json"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_disconnect_removes_tokens_and_notifies_worker(client, db_session, monkeypatch):
    user = await _create_user(db_session)
    access_expires_at, _ = await _store_token(
        db_session,
        user,
        account_id="channel-remove",
        expires_delta=timedelta(hours=1),
    )
    # Create worker app so notify is attempted
    from src.core.models.worker_app import WorkerApp
    worker_app = WorkerApp(
        base_url="https://worker-remove.example/api",
        webhook_url="https://worker-remove.example/hook",
        user_id=user.id,
    )
    db_session.add(worker_app)
    await db_session.commit()

    captured = {}

    class DeleteClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def delete(self, url, json=None, headers=None, **kwargs):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return DummyResponse(200, {})

    monkeypatch.setattr("src.api_v1.google_oauth.httpx.AsyncClient", DeleteClient)

    with _override_active_user(user):
        response = await client.delete("/api/v1/auth/google/account")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "disconnected"
    assert payload["account_id"] == "channel-remove"
    assert payload["worker_synced"] is True
    assert "oauth/tokens" in captured["url"]
    assert captured["json"] == {"provider": "youtube", "account_id": "channel-remove"}

    # Token should be removed
    service = OAuthTokenService(OAuthTokenRepository(db_session), get_settings().oauth_encryption_key)
    remaining = await service.get_tokens(YouTubeService.PROVIDER, user_id=user.id)
    assert remaining is None


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.api
async def test_disconnect_missing_tokens_returns_404(client, db_session):
    user = await _create_user(db_session)

    with _override_active_user(user):
        response = await client.delete("/api/v1/auth/google/account")

    assert response.status_code == 404
    assert response.json()["detail"] == "No YouTube tokens found"
