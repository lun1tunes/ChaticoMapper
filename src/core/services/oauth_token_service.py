"""Service for encrypting and persisting OAuth tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken

from src.core.repositories.oauth_token_repository import OAuthTokenRepository


@dataclass
class OAuthTokenData:
    provider: str
    account_id: str
    user_id: str | UUID
    access_token: str
    refresh_token: Optional[str]
    scope: Optional[str]
    access_token_expires_at: Optional[datetime]
    refresh_token_expires_at: Optional[datetime]


class OAuthTokenService:
    """Encrypt/decrypt token material and persist via repository."""

    def __init__(self, repo: OAuthTokenRepository, encryption_key: str):
        self.repo = repo
        self.fernet = Fernet(encryption_key)

    def _encrypt(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return self.fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def _decrypt(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            return self.fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            # Treat invalid data as missing so callers can re-authorize
            return None

    async def store_tokens(
        self,
        *,
        provider: str,
        account_id: str,
        user_id: str | UUID,
        access_token: str,
        refresh_token: Optional[str],
        scope: Optional[str],
        access_token_expires_at: Optional[datetime],
        refresh_token_expires_at: Optional[datetime] = None,
    ) -> OAuthTokenData:
        encrypted_access = self._encrypt(access_token)
        encrypted_refresh = self._encrypt(refresh_token)

        token = await self.repo.upsert(
            provider=provider,
            account_id=account_id,
            user_id=user_id,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            scope=scope,
            access_token_expires_at=access_token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
        )

        return OAuthTokenData(
            provider=token.provider,
            account_id=token.account_id,
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            scope=token.scope,
            access_token_expires_at=token.access_token_expires_at,
            refresh_token_expires_at=token.refresh_token_expires_at,
        )

    async def get_tokens(
        self,
        provider: str,
        user_id: str | UUID,
        account_id: Optional[str] = None,
    ) -> Optional[OAuthTokenData]:
        if not user_id:
            return None
        token = await self.repo.get_latest(provider, user_id, account_id)
        if not token:
            return None

        access = self._decrypt(token.encrypted_access_token)
        refresh = self._decrypt(token.encrypted_refresh_token)
        if not access:
            return None

        return OAuthTokenData(
            provider=token.provider,
            account_id=token.account_id,
            user_id=user_id,
            access_token=access,
            refresh_token=refresh,
            scope=token.scope,
            access_token_expires_at=token.access_token_expires_at,
            refresh_token_expires_at=token.refresh_token_expires_at,
        )

    async def update_access_token(
        self,
        *,
        provider: str,
        account_id: str,
        user_id: str | UUID,
        access_token: str,
        refresh_token: Optional[str],
        access_token_expires_at: Optional[datetime],
    ) -> Optional[OAuthTokenData]:
        encrypted_access = self._encrypt(access_token)
        encrypted_refresh = self._encrypt(refresh_token)

        token = await self.repo.update_access_token(
            provider=provider,
            account_id=account_id,
            user_id=user_id,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            access_token_expires_at=access_token_expires_at,
        )
        if not token:
            return None

        return OAuthTokenData(
            provider=token.provider,
            account_id=token.account_id,
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            scope=token.scope,
            access_token_expires_at=token.access_token_expires_at,
            refresh_token_expires_at=token.refresh_token_expires_at,
        )
