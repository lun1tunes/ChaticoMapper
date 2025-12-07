"""YouTube API authentication helper."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import httpx

from src.core.config import Settings
from src.core.services.oauth_token_service import OAuthTokenData, OAuthTokenService

logger = logging.getLogger(__name__)


class MissingYouTubeAuth(Exception):
    """Raised when no usable YouTube OAuth credentials are available."""


class QuotaExceeded(Exception):
    """Raised when YouTube API returns quota errors."""


class YouTubeService:
    """Wrapper that manages OAuth tokens and exposes channel-aware helpers."""

    PROVIDER = "google"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

    def __init__(
        self,
        token_service: OAuthTokenService,
        settings: Settings,
        http_client: type[httpx.AsyncClient] = httpx.AsyncClient,
    ):
        self.token_service = token_service
        self.settings = settings
        self._http_client = http_client

    async def get_or_refresh_credentials(
        self, user_id: str | UUID, account_id: Optional[str] = None
    ) -> OAuthTokenData:
        """
        Load valid credentials, refreshing or using env refresh token when needed.

        Raises:
            MissingYouTubeAuth: when no credentials or refresh mechanism is available
        """
        token = await self.token_service.get_tokens(self.PROVIDER, user_id, account_id)
        if not token:
            raise MissingYouTubeAuth("User has not connected YouTube.")

        if token.expires_at and token.expires_at <= datetime.now(timezone.utc) + timedelta(seconds=30):
            if token.refresh_token:
                refreshed = await self._refresh_token(user_id, token.refresh_token, token.account_id)
                if refreshed:
                    return refreshed
            raise MissingYouTubeAuth("Stored YouTube token expired and no refresh token available.")

        return token

    async def _refresh_token(
        self, user_id: str | UUID, refresh_token: Optional[str], account_id: Optional[str]
    ) -> Optional[OAuthTokenData]:
        if not refresh_token:
            return None

        payload = {
            "client_id": self.settings.youtube_client_id,
            "client_secret": self.settings.youtube_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        async with self._http_client(timeout=20.0) as client:
            resp = await client.post(self.TOKEN_URL, data=payload)
            if resp.status_code != 200:
                logger.error("Failed to refresh YouTube token: %s %s", resp.status_code, resp.text)
                return None

            data = resp.json()
            access_token = data.get("access_token")
            new_refresh = data.get("refresh_token") or refresh_token
            expires_in = data.get("expires_in")
            scope = data.get("scope")

            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
                if expires_in
                else None
            )

            # Need account id to store; fetch if missing
            target_account_id = account_id or await self._fetch_channel_id(access_token)
            if not target_account_id:
                logger.error("Could not determine YouTube channel id during refresh")
                return None

            return await self.token_service.store_tokens(
                provider=self.PROVIDER,
                account_id=target_account_id,
                user_id=user_id,
                access_token=access_token,
                refresh_token=new_refresh,
                scope=scope,
                expires_at=expires_at,
            )

    async def _fetch_channel_id(self, access_token: str) -> Optional[str]:
        params = {"part": "id", "mine": "true"}
        headers = {"Authorization": f"Bearer {access_token}"}

        async with self._http_client(timeout=20.0) as client:
            resp = await client.get(self.CHANNELS_URL, params=params, headers=headers)
            if resp.status_code == 403 and "quotaExceeded" in resp.text:
                raise QuotaExceeded("YouTube quota exceeded")
            if resp.status_code != 200:
                logger.error("Failed to fetch channel id: %s %s", resp.status_code, resp.text)
                return None
            data = resp.json()
            items = data.get("items") or []
            if not items:
                return None
            return items[0].get("id")
