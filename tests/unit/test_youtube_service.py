import base64
from datetime import datetime, timedelta, timezone

import pytest

from src.core.models.user import User
from src.core.repositories.oauth_token_repository import OAuthTokenRepository
from src.core.services.oauth_token_service import OAuthTokenService
from src.core.services.oauth_token_service import OAuthTokenData
from src.core.services.youtube_service import MissingYouTubeAuth, YouTubeService
from uuid import uuid4


def _key() -> str:
    return base64.urlsafe_b64encode(b"1" * 32).decode()


async def _create_user(db_session) -> User:
    user = User(
        username=f"yt_user_{uuid4().hex}",
        full_name="YT User",
        hashed_password="test_hash",
        role="basic",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class _FakeHttpClient:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, data=None):
        # Simulate refresh token exchange
        return _Response(
            200,
            {
                "access_token": "new-access",
                "refresh_token": data.get("refresh_token"),
                "expires_in": 3600,
                "scope": "scope1",
            },
        )

    async def get(self, url: str, params=None, headers=None):
        # Simulate channel lookup
        return _Response(200, {"items": [{"id": "channel-id"}]})


class _Response:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _StubSettings:
    def __init__(self, refresh_token: str | None):
        self.youtube_client_id = "id"
        self.youtube_client_secret = "secret"
        self.youtube_redirect_uri = "http://localhost/cb"
        self.youtube_refresh_token = refresh_token


class _StubTokenService:
    def __init__(self, token):
        self.token = token
        self.stored_kwargs = None

    async def get_tokens(self, provider, user_id, account_id=None):
        return self.token

    async def store_tokens(self, **kwargs):
        self.stored_kwargs = kwargs
        return self.token.__class__(
            provider=kwargs["provider"],
            account_id=kwargs["account_id"],
            user_id=kwargs["user_id"],
            instagram_user_id=kwargs.get("instagram_user_id"),
            username=kwargs.get("username"),
            access_token=kwargs["access_token"],
            refresh_token=kwargs["refresh_token"],
            scope=kwargs.get("scope"),
            access_token_expires_at=kwargs.get("access_token_expires_at"),
            refresh_token_expires_at=kwargs.get("refresh_token_expires_at"),
        )


@pytest.mark.asyncio
async def test_refresh_with_env_token_when_missing(db_session, monkeypatch):
    repo = OAuthTokenRepository(db_session)
    token_service = OAuthTokenService(repo, _key())
    user = await _create_user(db_session)
    settings = _StubSettings(refresh_token=None)

    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    await token_service.store_tokens(
        provider="youtube",
        account_id="channel-1",
        user_id=user.id,
        access_token="old-access",
        refresh_token="stored-refresh",
        scope="scope1",
        access_token_expires_at=expired,
    )

    svc = YouTubeService(token_service, settings=settings, http_client=_FakeHttpClient)
    token = await svc.get_or_refresh_credentials(user.id)
    assert token.access_token == "new-access"
    assert token.refresh_token == "stored-refresh"
    assert token.account_id == "channel-1"


@pytest.mark.asyncio
async def test_missing_tokens_without_refresh_raises(db_session, monkeypatch):
    repo = OAuthTokenRepository(db_session)
    token_service = OAuthTokenService(repo, _key())
    settings = _StubSettings(refresh_token=None)

    svc = YouTubeService(token_service, settings=settings, http_client=_FakeHttpClient)
    with pytest.raises(MissingYouTubeAuth):
        user = await _create_user(db_session)
        await svc.get_or_refresh_credentials(user.id)


@pytest.mark.asyncio
async def test_refresh_updates_refresh_token_expiry(monkeypatch):
    """Ensure refresh_token_expires_in is applied on refresh."""
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    token_data = OAuthTokenData(
        provider="youtube",
        account_id="channel-1",
        user_id=uuid4(),
        instagram_user_id=None,
        username=None,
        access_token="old",
        refresh_token="stored-refresh",
        scope="scope1",
        access_token_expires_at=expired,
        refresh_token_expires_at=None,
    )
    settings = _StubSettings(refresh_token=None)

    class _RefreshHttpClient(_FakeHttpClient):
        async def post(self, url: str, data=None):
            return _Response(
                200,
                {
                    "access_token": "new-access",
                    "refresh_token": data.get("refresh_token"),
                    "expires_in": 3600,
                    "refresh_token_expires_in": 7200,
                    "scope": "scope1",
                },
            )

    token_service = _StubTokenService(token_data)
    svc = YouTubeService(token_service, settings=settings, http_client=_RefreshHttpClient)

    refreshed = await svc.get_or_refresh_credentials(user_id=token_data.user_id, account_id="channel-1")
    assert refreshed.refresh_token == "stored-refresh"
    stored_args = token_service.stored_kwargs
    assert stored_args is not None
    assert stored_args["refresh_token_expires_at"] is not None
    delta = stored_args["refresh_token_expires_at"] - datetime.now(timezone.utc)
    assert timedelta(minutes=100) < delta < timedelta(minutes=140)
