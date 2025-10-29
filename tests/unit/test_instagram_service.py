"""Unit tests for Instagram service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import Response, HTTPStatusError

from app.services import InstagramService
from app.config import Settings


@pytest.mark.unit
class TestInstagramService:
    """Test cases for InstagramService."""

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return Settings(
            instagram_app_id="test_app_id",
            instagram_app_secret="test_app_secret",
            instagram_access_token="test_access_token",
            instagram_api_base_url="https://graph.instagram.com",
            instagram_api_timeout=30,
            instagram_rate_limit=200,
        )

    @pytest.fixture
    def instagram_service(self, settings):
        """Create InstagramService instance."""
        return InstagramService()

    @pytest.fixture
    def sample_media_info(self):
        """Sample media info response."""
        return {
            "id": "test_media_id",
            "owner": {"id": "test_owner_id"},
            "media_type": "IMAGE",
            "media_url": "https://example.com/image.jpg",
            "timestamp": "2024-01-01T00:00:00Z",
        }

    @pytest.mark.asyncio
    async def test_get_media_info_success(self, instagram_service, sample_media_info):
        """Test successful media info retrieval."""
        with (
            patch("httpx.AsyncClient") as mock_client_class,
            patch.object(instagram_service, "_rate_limiter", AsyncMock()),
        ):
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = MagicMock(return_value=sample_media_info)
            mock_response.raise_for_status = MagicMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await instagram_service.get_media_info("test_media_id")

            assert result is not None
            assert result.id == sample_media_info["id"]
            assert result.owner == sample_media_info["owner"]
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_media_info_api_error(self, instagram_service):
        """Test media info retrieval with API error."""
        with (
            patch("httpx.AsyncClient") as mock_client_class,
            patch.object(instagram_service, "_rate_limiter", AsyncMock()),
        ):
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 400
            mock_response.raise_for_status = MagicMock(side_effect=HTTPStatusError(
                "Bad Request", request=None, response=mock_response
            ))
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await instagram_service.get_media_info("invalid_media_id")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_media_info_network_error(self, instagram_service):
        """Test media info retrieval with network error."""
        with (
            patch("httpx.AsyncClient") as mock_client_class,
            patch.object(instagram_service, "_rate_limiter", AsyncMock()),
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Network error"))
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await instagram_service.get_media_info("test_media_id")
            assert result is None

    def test_extract_owner_id_success(self, instagram_service, sample_media_info):
        """Test successful owner ID extraction."""
        from app.schemas import InstagramMedia

        media = InstagramMedia(
            id=sample_media_info["id"],
            owner=sample_media_info["owner"],
            media_type=sample_media_info.get("media_type"),
            media_url=sample_media_info.get("media_url"),
            permalink=sample_media_info.get("permalink"),
        )

        result = instagram_service.extract_owner_id(media)
        assert result == "test_owner_id"

    def test_extract_owner_id_missing_owner(self, instagram_service):
        """Test owner ID extraction with missing owner."""
        from app.schemas import InstagramMedia

        media = InstagramMedia(id="test_media_id")

        with pytest.raises(ValueError, match="Owner information not found"):
            instagram_service.extract_owner_id(media)

    def test_extract_owner_id_missing_owner_id(self, instagram_service):
        """Test owner ID extraction with missing owner ID."""
        from app.schemas import InstagramMedia

        media = InstagramMedia(
            id="test_media_id",
            owner={},
        )

        with pytest.raises(ValueError, match="Owner information not found"):
            instagram_service.extract_owner_id(media)

    @pytest.mark.asyncio
    async def test_get_media_info_rate_limiting(self, instagram_service):
        """Test rate limiting behavior."""
        with (
            patch("httpx.AsyncClient") as mock_client_class,
            patch.object(instagram_service, "_rate_limiter", AsyncMock()),
        ):
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "60"}
            mock_response.raise_for_status = MagicMock(side_effect=HTTPStatusError(
                "Too Many Requests", request=None, response=mock_response
            ))
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await instagram_service.get_media_info("test_media_id")
            assert result is None

    @pytest.mark.asyncio
    async def test_get_media_info_timeout(self, instagram_service):
        """Test timeout handling."""
        with (
            patch("httpx.AsyncClient") as mock_client_class,
            patch.object(instagram_service, "_rate_limiter", AsyncMock()),
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=TimeoutError("Request timeout"))
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await instagram_service.get_media_info("test_media_id")
            assert result is None

    def test_service_configuration(self, instagram_service):
        """Test service configuration."""
        assert instagram_service.base_url == "https://graph.instagram.com"
        assert instagram_service.access_token is not None
        assert instagram_service.timeout == 30
        assert instagram_service.rate_limit == 200
