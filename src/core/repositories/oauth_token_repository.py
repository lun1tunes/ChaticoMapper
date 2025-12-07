"""Repository for OAuth token persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.oauth_token import OAuthToken
from src.core.repositories.base import BaseRepository


class OAuthTokenRepository(BaseRepository[OAuthToken]):
    """Data access for OAuth tokens."""

    def __init__(self, session: AsyncSession):
        super().__init__(OAuthToken, session)

    async def get_latest(
        self, provider: str, account_id: Optional[str] = None
    ) -> Optional[OAuthToken]:
        stmt = select(OAuthToken).where(OAuthToken.provider == provider)
        if account_id:
            stmt = stmt.where(OAuthToken.account_id == account_id)
        stmt = stmt.order_by(OAuthToken.updated_at.desc(), OAuthToken.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def upsert(
        self,
        *,
        provider: str,
        account_id: str,
        encrypted_access_token: str,
        encrypted_refresh_token: Optional[str],
        scope: Optional[str],
        expires_at: Optional[datetime],
    ) -> OAuthToken:
        existing = await self._get_by_provider_account(provider, account_id)
        if existing:
            existing.encrypted_access_token = encrypted_access_token
            existing.encrypted_refresh_token = encrypted_refresh_token
            existing.scope = scope
            existing.expires_at = expires_at
            await self.session.flush()
            return existing

        token = OAuthToken(
            provider=provider,
            account_id=account_id,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            scope=scope,
            expires_at=expires_at,
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def update_access_token(
        self,
        *,
        provider: str,
        account_id: str,
        encrypted_access_token: str,
        encrypted_refresh_token: Optional[str],
        expires_at: Optional[datetime],
    ) -> Optional[OAuthToken]:
        token = await self._get_by_provider_account(provider, account_id)
        if not token:
            return None

        token.encrypted_access_token = encrypted_access_token
        token.encrypted_refresh_token = encrypted_refresh_token
        token.expires_at = expires_at
        await self.session.flush()
        return token

    async def _get_by_provider_account(
        self, provider: str, account_id: str
    ) -> Optional[OAuthToken]:
        result = await self.session.execute(
            select(OAuthToken).where(
                OAuthToken.provider == provider, OAuthToken.account_id == account_id
            )
        )
        return result.scalar_one_or_none()

