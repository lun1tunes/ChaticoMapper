"""Instagram Graph API service for fetching media information."""

import logging
from typing import Optional

import httpx
from httpx import AsyncClient, HTTPStatusError, RequestError

logger = logging.getLogger(__name__)


class InstagramAPIService:
    """
    Service for interacting with Instagram Graph API.

    Provides methods to fetch media information, specifically owner_id
    for webhook routing.
    """

    def __init__(
        self,
        access_token: str,
        api_base_url: str = "https://graph.instagram.com/v23.0",
        timeout: float = 10.0,
    ):
        """
        Initialize Instagram API service.

        Args:
            access_token: Instagram app access token
            api_base_url: Base URL for Instagram Graph API
            timeout: Request timeout in seconds
        """
        self.access_token = access_token
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[AsyncClient] = None

    async def get_client(self) -> AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("Instagram API client closed")

    async def get_media_owner(self, media_id: str) -> dict:
        """
        Get owner information for a media item.

        This is a lightweight request that only fetches the owner field,
        optimized for fast webhook routing.

        Args:
            media_id: Instagram media ID

        Returns:
            dict with:
                - success (bool): Whether the request succeeded
                - owner_id (str): Instagram account ID (if success=True)
                - username (str): Instagram username (if success=True)
                - error (str): Error message (if success=False)
                - status_code (int): HTTP status code
        """
        url = f"{self.api_base_url}/{media_id}"
        params = {
            "access_token": self.access_token,
            "fields": "owner,username",  # Minimal fields for fast response
        }

        try:
            client = await self.get_client()
            response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()

                # Extract owner info
                owner_data = data.get("owner", {})
                owner_id = owner_data.get("id") if isinstance(owner_data, dict) else owner_data
                username = data.get("username")

                logger.debug(
                    f"Instagram API success: media_id={media_id} -> owner_id={owner_id}, "
                    f"username={username}"
                )

                return {
                    "success": True,
                    "owner_id": owner_id,
                    "username": username,
                    "status_code": response.status_code,
                }

            else:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("error", {}).get("message", "Unknown error")

                logger.warning(
                    f"Instagram API error: media_id={media_id}, "
                    f"status={response.status_code}, error={error_msg}"
                )

                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                    "error_data": error_data,
                }

        except HTTPStatusError as e:
            logger.error(
                f"Instagram API HTTP error: media_id={media_id}, "
                f"status={e.response.status_code}"
            )
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}",
                "status_code": e.response.status_code,
            }

        except RequestError as e:
            logger.error(f"Instagram API request error: media_id={media_id}, error={str(e)}")
            return {
                "success": False,
                "error": f"Request error: {str(e)}",
                "status_code": None,
            }

        except Exception as e:
            logger.exception(f"Instagram API unexpected error: media_id={media_id}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "status_code": None,
            }

    async def get_media_info_full(self, media_id: str) -> dict:
        """
        Get full media information.

        This fetches comprehensive media details including permalink, media type,
        caption, etc. Use this when you need more than just owner info.

        Args:
            media_id: Instagram media ID

        Returns:
            dict with success status and full media data
        """
        url = f"{self.api_base_url}/{media_id}"
        params = {
            "access_token": self.access_token,
            "fields": (
                "id,owner,username,permalink,media_type,media_url,"
                "caption,timestamp,comments_count,like_count"
            ),
        }

        try:
            client = await self.get_client()
            response = await client.get(url, params=params)

            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Instagram API full info success: media_id={media_id}")

                return {
                    "success": True,
                    "media_info": data,
                    "status_code": response.status_code,
                }

            else:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("error", {}).get("message", "Unknown error")

                logger.warning(
                    f"Instagram API full info error: media_id={media_id}, "
                    f"status={response.status_code}, error={error_msg}"
                )

                return {
                    "success": False,
                    "error": error_msg,
                    "status_code": response.status_code,
                    "error_data": error_data,
                }

        except Exception as e:
            logger.exception(f"Instagram API full info unexpected error: media_id={media_id}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "status_code": None,
            }

    async def verify_access_token(self) -> bool:
        """
        Verify that the access token is valid.

        Returns:
            True if token is valid, False otherwise
        """
        url = f"{self.api_base_url}/me"
        params = {"access_token": self.access_token}

        try:
            client = await self.get_client()
            response = await client.get(url, params=params)

            if response.status_code == 200:
                logger.info("Instagram access token verified successfully")
                return True
            else:
                logger.warning(
                    f"Instagram access token verification failed: "
                    f"status={response.status_code}"
                )
                return False

        except Exception as e:
            logger.error(f"Instagram access token verification error: {e}")
            return False
