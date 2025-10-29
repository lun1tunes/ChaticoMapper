"""Unit tests for routing service."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services import RoutingService
from app.config import Settings


@pytest.mark.unit
class TestRoutingService:
    """Test cases for RoutingService."""

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return Settings(
            rabbitmq_url="amqp://guest:guest@localhost:5672/",
            rabbitmq_exchange="test_exchange",
        )

    @pytest.fixture
    def mock_worker_app_repository(self):
        """Create mock worker app repository."""
        return AsyncMock()

    @pytest.fixture
    def routing_service(self, mock_worker_app_repository):
        """Create RoutingService instance."""
        return RoutingService(mock_worker_app_repository)

    @pytest.fixture
    def sample_worker_app(self):
        """Sample worker app data."""
        return {
            "id": str(uuid4()),
            "owner_id": "test_owner_id",
            "app_name": "Test Worker App",
            "base_url": "https://test-worker.example.com",
            "webhook_path": "/webhook",
            "queue_name": "test_queue",
            "is_active": True,
        }

    @pytest.mark.asyncio
    async def test_find_worker_app_by_owner_id_success(
        self, routing_service, mock_worker_app_repository, sample_worker_app
    ):
        """Test successful worker app lookup by owner ID."""
        mock_worker_app_repository.get_by_owner_id.return_value = sample_worker_app

        result = await routing_service.find_worker_app_by_owner_id("test_owner_id")

        assert result == sample_worker_app
        mock_worker_app_repository.get_by_owner_id.assert_called_once_with(
            "test_owner_id"
        )

    @pytest.mark.asyncio
    async def test_find_worker_app_by_owner_id_not_found(
        self, routing_service, mock_worker_app_repository
    ):
        """Test worker app lookup when not found."""
        mock_worker_app_repository.get_by_owner_id.return_value = None

        result = await routing_service.find_worker_app_by_owner_id(
            "nonexistent_owner_id"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_find_worker_app_by_owner_id_repository_error(
        self, routing_service, mock_worker_app_repository
    ):
        """Test worker app lookup with repository error."""
        mock_worker_app_repository.get_by_owner_id.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match="Database error"):
            await routing_service.find_worker_app_by_owner_id("test_owner_id")

    @pytest.mark.asyncio
    async def test_is_worker_app_healthy_active(
        self, routing_service, sample_worker_app
    ):
        """Test health check for active worker app."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await routing_service.is_worker_app_healthy(sample_worker_app)

            assert result is True
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_worker_app_healthy_inactive(self, routing_service):
        """Test health check for inactive worker app."""
        inactive_worker_app = {
            "id": str(uuid4()),
            "owner_id": "test_owner_id",
            "app_name": "Test Worker App",
            "base_url": "https://test-worker.example.com",
            "webhook_path": "/webhook",
            "queue_name": "test_queue",
            "is_active": False,
        }

        result = await routing_service.is_worker_app_healthy(inactive_worker_app)

        assert result is False

    @pytest.mark.asyncio
    async def test_is_worker_app_healthy_http_error(
        self, routing_service, sample_worker_app
    ):
        """Test health check with HTTP error."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            result = await routing_service.is_worker_app_healthy(sample_worker_app)

            assert result is False

    @pytest.mark.asyncio
    async def test_is_worker_app_healthy_timeout(
        self, routing_service, sample_worker_app
    ):
        """Test health check with timeout."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = TimeoutError("Request timeout")

            result = await routing_service.is_worker_app_healthy(sample_worker_app)

            assert result is False

    @pytest.mark.asyncio
    async def test_is_worker_app_healthy_network_error(
        self, routing_service, sample_worker_app
    ):
        """Test health check with network error."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = Exception("Network error")

            result = await routing_service.is_worker_app_healthy(sample_worker_app)

            assert result is False

    def test_build_webhook_url(self, routing_service, sample_worker_app):
        """Test webhook URL building."""
        expected_url = "https://test-worker.example.com/webhook"

        result = routing_service._build_webhook_url(sample_worker_app)

        assert result == expected_url

    def test_build_webhook_url_with_trailing_slash(self, routing_service):
        """Test webhook URL building with trailing slash in base URL."""
        worker_app = {
            "base_url": "https://test-worker.example.com/",
            "webhook_path": "/webhook",
        }

        expected_url = "https://test-worker.example.com/webhook"

        result = routing_service._build_webhook_url(worker_app)

        assert result == expected_url

    def test_build_webhook_url_without_leading_slash(self, routing_service):
        """Test webhook URL building without leading slash in webhook path."""
        worker_app = {
            "base_url": "https://test-worker.example.com",
            "webhook_path": "webhook",
        }

        expected_url = "https://test-worker.example.com/webhook"

        result = routing_service._build_webhook_url(worker_app)

        assert result == expected_url

    @pytest.mark.asyncio
    async def test_route_webhook_success(
        self, routing_service, mock_worker_app_repository, sample_worker_app
    ):
        """Test successful webhook routing."""
        mock_worker_app_repository.get_by_owner_id.return_value = sample_worker_app

        with patch.object(routing_service, "is_worker_app_healthy", return_value=True):
            webhook_payload = {"test": "data"}
            owner_id = "test_owner_id"

            result = await routing_service.route_webhook(webhook_payload, owner_id)

            assert result["status"] == "success"
            assert result["routed_to"] == "test_queue"
            assert "target_app_url" in result

    @pytest.mark.asyncio
    async def test_route_webhook_no_worker_app(
        self, routing_service, mock_worker_app_repository
    ):
        """Test webhook routing with no worker app found."""
        mock_worker_app_repository.get_by_owner_id.return_value = None

        webhook_payload = {"test": "data"}
        owner_id = "nonexistent_owner_id"

        result = await routing_service.route_webhook(webhook_payload, owner_id)

        assert result["status"] == "failed"
        assert "No worker app found" in result["error_details"]

    @pytest.mark.asyncio
    async def test_route_webhook_unhealthy_worker_app(
        self, routing_service, mock_worker_app_repository, sample_worker_app
    ):
        """Test webhook routing with unhealthy worker app."""
        mock_worker_app_repository.get_by_owner_id.return_value = sample_worker_app

        with patch.object(routing_service, "is_worker_app_healthy", return_value=False):
            webhook_payload = {"test": "data"}
            owner_id = "test_owner_id"

            result = await routing_service.route_webhook(webhook_payload, owner_id)

            assert result["status"] == "failed"
            assert "Worker app is not healthy" in result["error_details"]

    @pytest.mark.asyncio
    async def test_route_webhook_repository_error(
        self, routing_service, mock_worker_app_repository
    ):
        """Test webhook routing with repository error."""
        mock_worker_app_repository.get_by_owner_id.side_effect = Exception(
            "Database error"
        )

        webhook_payload = {"test": "data"}
        owner_id = "test_owner_id"

        result = await routing_service.route_webhook(webhook_payload, owner_id)

        assert result["status"] == "failed"
        assert "Database error" in result["error_details"]
