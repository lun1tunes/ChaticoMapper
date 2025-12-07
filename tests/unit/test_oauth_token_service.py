import base64
from datetime import datetime, timezone, timedelta

import pytest

from src.core.models.oauth_token import OAuthToken
from src.core.repositories.oauth_token_repository import OAuthTokenRepository
from src.core.services.oauth_token_service import OAuthTokenService


def _key() -> str:
    return base64.urlsafe_b64encode(b"0" * 32).decode()


@pytest.mark.asyncio
async def test_store_and_get_tokens(db_session):
    repo = OAuthTokenRepository(db_session)
    service = OAuthTokenService(repo, _key())

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    await service.store_tokens(
        provider="google",
        account_id="channel-1",
        access_token="access",
        refresh_token="refresh",
        scope="scope1",
        expires_at=expires,
    )

    fetched = await service.get_tokens("google", "channel-1")
    assert fetched is not None
    assert fetched.access_token == "access"
    assert fetched.refresh_token == "refresh"
    assert fetched.scope == "scope1"
    assert fetched.expires_at == expires


@pytest.mark.asyncio
async def test_update_access_token(db_session):
    repo = OAuthTokenRepository(db_session)
    service = OAuthTokenService(repo, _key())

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    await service.store_tokens(
        provider="google",
        account_id="channel-1",
        access_token="old",
        refresh_token="old-refresh",
        scope="scope1",
        expires_at=expires,
    )

    new_exp = datetime.now(timezone.utc) + timedelta(hours=2)
    updated = await service.update_access_token(
        provider="google",
        account_id="channel-1",
        access_token="new",
        refresh_token="new-refresh",
        expires_at=new_exp,
    )
    assert updated is not None
    assert updated.access_token == "new"
    assert updated.refresh_token == "new-refresh"
    assert updated.expires_at == new_exp

