"""Repository for OAuth token persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.oauth_token import OAuthToken
from src.core.repositories.base import BaseRepository


class OAuthTokenRepository(BaseRepository[OAuthToken]):
    """Data access for OAuth tokens."""

    def __init__(self, session: AsyncSession):
        super().__init__(OAuthToken, session)

    async def get_latest(
        self, provider: str, user_id: UUID | str, account_id: Optional[str] = None
    ) -> Optional[OAuthToken]:
        stmt = select(OAuthToken).where(OAuthToken.provider == provider)
        if user_id:
            stmt = stmt.where(OAuthToken.user_id == user_id)
        if account_id:
            stmt = stmt.where(OAuthToken.account_id == account_id)
        stmt = stmt.order_by(OAuthToken.updated_at.desc(), OAuthToken.created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_provider_account_id(
        self, provider: str, account_id: str
    ) -> Optional[OAuthToken]:
        stmt = (
            select(OAuthToken)
            .where(
                OAuthToken.provider == provider,
                OAuthToken.account_id == account_id,
            )
            .order_by(OAuthToken.updated_at.desc(), OAuthToken.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def upsert(
        self,
        *,
        provider: str,
        account_id: str,
        user_id: UUID | str,
        instagram_user_id: Optional[str] = None,
        username: Optional[str] = None,
        encrypted_access_token: str,
        encrypted_refresh_token: Optional[str],
        scope: Optional[str],
        access_token_expires_at: Optional[datetime],
        refresh_token_expires_at: Optional[datetime],
    ) -> OAuthToken:
        existing = await self._get_by_provider_account_user(provider, account_id, user_id)
        if existing:
            existing.encrypted_access_token = encrypted_access_token
            existing.encrypted_refresh_token = encrypted_refresh_token
            existing.scope = scope
            existing.access_token_expires_at = access_token_expires_at
            existing.refresh_token_expires_at = refresh_token_expires_at
            if instagram_user_id is not None:
                existing.instagram_user_id = instagram_user_id
            if username is not None:
                existing.username = username
            await self.session.flush()
            return existing

        token = OAuthToken(
            provider=provider,
            account_id=account_id,
            user_id=user_id,
            instagram_user_id=instagram_user_id,
            username=username,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            scope=scope,
            access_token_expires_at=access_token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def update_access_token(
        self,
        *,
        provider: str,
        account_id: str,
        user_id: UUID | str,
        encrypted_access_token: str,
        encrypted_refresh_token: Optional[str],
        access_token_expires_at: Optional[datetime],
    ) -> Optional[OAuthToken]:
        token = await self._get_by_provider_account_user(provider, account_id, user_id)
        if not token:
            return None

        token.encrypted_access_token = encrypted_access_token
        token.encrypted_refresh_token = encrypted_refresh_token
        token.access_token_expires_at = access_token_expires_at
        await self.session.flush()
        return token

    async def _get_by_provider_account_user(
        self, provider: str, account_id: str, user_id: UUID | str
    ) -> Optional[OAuthToken]:
        result = await self.session.execute(
            select(OAuthToken).where(
                OAuthToken.provider == provider,
                OAuthToken.account_id == account_id,
                OAuthToken.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_for_user(
        self,
        *,
        provider: str,
        user_id: UUID | str,
        account_id: Optional[str] = None,
    ) -> int:
        stmt = delete(OAuthToken).where(
            OAuthToken.provider == provider,
            OAuthToken.user_id == user_id,
        )
        if account_id:
            stmt = stmt.where(OAuthToken.account_id == account_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount or 0
