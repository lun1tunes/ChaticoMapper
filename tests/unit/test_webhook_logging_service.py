"""Unit tests for webhook logging service."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.services import WebhookLoggingService
from app.config import Settings


@pytest.mark.unit
class TestWebhookLoggingService:
    """Test cases for WebhookLoggingService."""

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return Settings(
            database_url="sqlite+aiosqlite:///:memory:",
        )

    @pytest.fixture
    def mock_webhook_log_repository(self):
        """Create mock webhook log repository."""
        return AsyncMock()

    @pytest.fixture
    def webhook_logging_service(self, mock_webhook_log_repository):
        """Create WebhookLoggingService instance."""
        return WebhookLoggingService(mock_webhook_log_repository)

    @pytest.fixture
    def sample_webhook_log(self):
        """Sample webhook log data."""
        return {
            "id": str(uuid4()),
            "webhook_id": str(uuid4()),
            "owner_id": "test_owner_id",
            "worker_app_id": str(uuid4()),
            "target_app_name": "Test Worker App",
            "processing_status": "success",
            "error_message": None,
            "processing_time_ms": 150,
            "created_at": datetime.now(timezone.utc),
        }

    @pytest.mark.asyncio
    async def test_log_webhook_processing_success(
        self, webhook_logging_service, mock_webhook_log_repository, sample_webhook_log
    ):
        """Test successful webhook processing logging."""
        mock_webhook_log_repository.create.return_value = sample_webhook_log

        webhook_id = str(uuid4())
        owner_id = "test_owner_id"
        worker_app_id = str(uuid4())
        target_app_name = "Test Worker App"
        status = "success"
        processing_time_ms = 150
        error_message = None

        result = await webhook_logging_service.log_webhook_processing(
            webhook_id,
            owner_id,
            worker_app_id,
            target_app_name,
            status,
            processing_time_ms,
            error_message,
        )

        assert result is None
        mock_webhook_log_repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_webhook_processing_with_error(
        self, webhook_logging_service, mock_webhook_log_repository
    ):
        """Test webhook processing logging with error."""
        webhook_id = str(uuid4())
        owner_id = "test_owner_id"
        worker_app_id = str(uuid4())
        target_app_name = "Test Worker App"
        status = "failed"
        processing_time_ms = 200
        error_message = "Test error message"

        await webhook_logging_service.log_webhook_processing(
            webhook_id,
            owner_id,
            worker_app_id,
            target_app_name,
            status,
            processing_time_ms,
            error_message,
        )

        mock_webhook_log_repository.create.assert_called_once()
        call_args = mock_webhook_log_repository.create.call_args[0][0]
        assert call_args["error_message"] == error_message
        assert call_args["processing_status"] == status

    @pytest.mark.asyncio
    async def test_log_webhook_processing_repository_error(
        self, webhook_logging_service, mock_webhook_log_repository
    ):
        """Test webhook processing logging with repository error."""
        mock_webhook_log_repository.create.side_effect = Exception("Database error")

        webhook_id = str(uuid4())
        owner_id = "test_owner_id"
        worker_app_id = str(uuid4())
        target_app_name = "Test Worker App"
        status = "success"
        processing_time_ms = 150
        error_message = None

        # Should not raise exception, just log the error
        result = await webhook_logging_service.log_webhook_processing(
            webhook_id,
            owner_id,
            worker_app_id,
            target_app_name,
            status,
            processing_time_ms,
            error_message,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_webhook_stats_success(
        self, webhook_logging_service, mock_webhook_log_repository
    ):
        """Test successful webhook stats retrieval."""
        mock_stats = {
            "total": 100,
            "success": 95,
            "failed": 5,
            "routed": 90,
        }
        mock_webhook_log_repository.get_stats.return_value = mock_stats

        result = await webhook_logging_service.get_webhook_stats()

        assert result == mock_stats
        mock_webhook_log_repository.get_stats.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_webhook_stats_repository_error(
        self, webhook_logging_service, mock_webhook_log_repository
    ):
        """Test webhook stats retrieval with repository error."""
        mock_webhook_log_repository.get_stats.side_effect = Exception("Database error")

        result = await webhook_logging_service.get_webhook_stats()

        # Should return default stats on error
        expected = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "routed": 0,
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_webhook_logs_success(
        self, webhook_logging_service, mock_webhook_log_repository
    ):
        """Test successful webhook logs retrieval."""
        mock_logs = [
            {
                "id": str(uuid4()),
                "webhook_id": str(uuid4()),
                "owner_id": "test_owner_id",
                "processing_status": "success",
                "created_at": datetime.now(timezone.utc),
            }
        ]
        mock_webhook_log_repository.list.return_value = mock_logs

        result = await webhook_logging_service.get_webhook_logs(
            limit=10, offset=0, status="success", worker_app_id=str(uuid4())
        )

        assert result == mock_logs
        mock_webhook_log_repository.list.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_webhook_logs_repository_error(
        self, webhook_logging_service, mock_webhook_log_repository
    ):
        """Test webhook logs retrieval with repository error."""
        mock_webhook_log_repository.list.side_effect = Exception("Database error")

        result = await webhook_logging_service.get_webhook_logs()

        # Should return empty list on error
        assert result == []

    @pytest.mark.asyncio
    async def test_get_webhook_logs_with_filters(
        self, webhook_logging_service, mock_webhook_log_repository
    ):
        """Test webhook logs retrieval with filters."""
        mock_logs = []
        mock_webhook_log_repository.list.return_value = mock_logs

        worker_app_id = str(uuid4())
        result = await webhook_logging_service.get_webhook_logs(
            limit=20, offset=10, status="failed", worker_app_id=worker_app_id
        )

        mock_webhook_log_repository.list.assert_called_once_with(
            limit=20, offset=10, status="failed", worker_app_id=worker_app_id
        )

    @pytest.mark.asyncio
    async def test_get_webhook_logs_default_params(
        self, webhook_logging_service, mock_webhook_log_repository
    ):
        """Test webhook logs retrieval with default parameters."""
        mock_logs = []
        mock_webhook_log_repository.list.return_value = mock_logs

        result = await webhook_logging_service.get_webhook_logs()

        mock_webhook_log_repository.list.assert_called_once_with(
            limit=100, offset=0, status=None, worker_app_id=None
        )

    @pytest.mark.asyncio
    async def test_log_webhook_processing_with_none_values(
        self, webhook_logging_service, mock_webhook_log_repository
    ):
        """Test webhook processing logging with None values."""
        webhook_id = str(uuid4())
        owner_id = "test_owner_id"
        worker_app_id = None
        target_app_name = None
        status = "failed"
        processing_time_ms = None
        error_message = "Test error"

        await webhook_logging_service.log_webhook_processing(
            webhook_id,
            owner_id,
            worker_app_id,
            target_app_name,
            status,
            processing_time_ms,
            error_message,
        )

        mock_webhook_log_repository.create.assert_called_once()
        call_args = mock_webhook_log_repository.create.call_args[0][0]
        assert call_args["worker_app_id"] is None
        assert call_args["target_app_name"] is None
        assert call_args["processing_time_ms"] is None
