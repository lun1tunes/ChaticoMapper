import base64
from datetime import datetime, timedelta, timezone

import pytest

from src.core.repositories.oauth_token_repository import OAuthTokenRepository
from src.core.services.oauth_token_service import OAuthTokenService
from src.core.services.youtube_service import MissingYouTubeAuth, YouTubeService


def _key() -> str:
    return base64.urlsafe_b64encode(b"1" * 32).decode()


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


@pytest.mark.asyncio
async def test_refresh_with_env_token_when_missing(db_session, monkeypatch):
    repo = OAuthTokenRepository(db_session)
    token_service = OAuthTokenService(repo, _key())
    settings = _StubSettings(refresh_token="env-refresh")

    svc = YouTubeService(token_service, settings=settings, http_client=_FakeHttpClient)
    token = await svc.get_or_refresh_credentials()
    assert token.access_token == "new-access"
    assert token.refresh_token == "env-refresh"
    assert token.account_id == "channel-id"


@pytest.mark.asyncio
async def test_missing_tokens_without_refresh_raises(db_session, monkeypatch):
    repo = OAuthTokenRepository(db_session)
    token_service = OAuthTokenService(repo, _key())
    settings = _StubSettings(refresh_token=None)

    svc = YouTubeService(token_service, settings=settings, http_client=_FakeHttpClient)
    with pytest.raises(MissingYouTubeAuth):
        await svc.get_or_refresh_credentials()

