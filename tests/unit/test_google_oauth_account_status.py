from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.api_v1.google_oauth import account_status
from src.core.models.user import User
from src.core.services.oauth_token_service import OAuthTokenData


class _StubTokenService:
    def __init__(self, token: OAuthTokenData | None):
        self._token = token

    async def get_tokens(self, provider, user_id, account_id=None):
        return self._token


@pytest.mark.asyncio
async def test_account_status_disconnected_when_expired():
    user = User(id=uuid4(), username="u1", full_name="", hashed_password="h", role="basic")
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = OAuthTokenData(
        provider="youtube",
        account_id="acc",
        user_id=user.id,
        instagram_user_id=None,
        username=None,
        access_token="a",
        refresh_token=None,
        scope="s",
        access_token_expires_at=expired,
        refresh_token_expires_at=None,
    )
    service = _StubTokenService(token)

    resp = await account_status(current_user=user, token_service=service)

    assert resp["connected"] is False
    assert resp["access_token_valid"] is False
    assert resp["refresh_token_valid"] is False


@pytest.mark.asyncio
async def test_account_status_connected_when_valid():
    user = User(id=uuid4(), username="u2", full_name="", hashed_password="h", role="basic")
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token = OAuthTokenData(
        provider="youtube",
        account_id="acc",
        user_id=user.id,
        instagram_user_id=None,
        username=None,
        access_token="a",
        refresh_token="r",
        scope="s",
        access_token_expires_at=future,
        refresh_token_expires_at=None,
    )
    service = _StubTokenService(token)

    resp = await account_status(current_user=user, token_service=service)

    assert resp["connected"] is True
    assert resp["access_token_valid"] is True


@pytest.mark.asyncio
async def test_account_status_connected_when_access_expired_but_refresh_valid():
    user = User(id=uuid4(), username="u3", full_name="", hashed_password="h", role="basic")
    expired = datetime.now(timezone.utc) - timedelta(minutes=5)
    refresh_future = datetime.now(timezone.utc) + timedelta(days=7)
    token = OAuthTokenData(
        provider="youtube",
        account_id="acc",
        user_id=user.id,
        instagram_user_id=None,
        username=None,
        access_token="a",
        refresh_token="r",
        scope="s",
        access_token_expires_at=expired,
        refresh_token_expires_at=refresh_future,
    )
    service = _StubTokenService(token)

    resp = await account_status(current_user=user, token_service=service)

    assert resp["connected"] is True
    assert resp["access_token_valid"] is False
    assert resp["refresh_token_valid"] is True
    assert resp["needs_refresh"] is True
