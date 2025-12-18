import base64
from datetime import datetime, timezone, timedelta

import pytest

from src.core.models.user import User
from src.core.models.oauth_token import OAuthToken
from src.core.repositories.oauth_token_repository import OAuthTokenRepository
from src.core.services.oauth_token_service import OAuthTokenService
from uuid import uuid4


def _key() -> str:
    return base64.urlsafe_b64encode(b"0" * 32).decode()


async def _create_user(db_session) -> User:
    user = User(
        username=f"test_user_{uuid4().hex}",
        full_name="Test User",
        hashed_password="test_hash",
        role="basic",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_store_and_get_tokens(db_session):
    repo = OAuthTokenRepository(db_session)
    service = OAuthTokenService(repo, _key())
    user = await _create_user(db_session)

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    await service.store_tokens(
        provider="google",
        account_id="channel-1",
        user_id=user.id,
        access_token="access",
        refresh_token="refresh",
        scope="scope1",
        access_token_expires_at=expires,
    )

    fetched = await service.get_tokens("google", user.id, "channel-1")
    assert fetched is not None
    assert fetched.access_token == "access"
    assert fetched.refresh_token == "refresh"
    assert fetched.scope == "scope1"
    assert fetched.access_token_expires_at.replace(tzinfo=None) == expires.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_update_access_token(db_session):
    repo = OAuthTokenRepository(db_session)
    service = OAuthTokenService(repo, _key())
    user = await _create_user(db_session)

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    await service.store_tokens(
        provider="google",
        account_id="channel-1",
        user_id=user.id,
        access_token="old",
        refresh_token="old-refresh",
        scope="scope1",
        access_token_expires_at=expires,
    )

    new_exp = datetime.now(timezone.utc) + timedelta(hours=2)
    updated = await service.update_access_token(
        provider="google",
        account_id="channel-1",
        user_id=user.id,
        access_token="new",
        refresh_token="new-refresh",
        access_token_expires_at=new_exp,
    )
    assert updated is not None
    assert updated.access_token == "new"
    assert updated.refresh_token == "new-refresh"
    assert updated.access_token_expires_at.replace(tzinfo=None) == new_exp.replace(tzinfo=None)
