"""Unit tests for ProcessWebhookUseCase."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.use_cases import ProcessWebhookUseCase
from app.schemas import WebhookPayload, RoutingResponse


@pytest.mark.unit
class TestProcessWebhookUseCase:
    """Test cases for ProcessWebhookUseCase."""

    @pytest.fixture
    def mock_instagram_service(self):
        """Create mock Instagram service."""
        return AsyncMock()

    @pytest.fixture
    def mock_routing_service(self):
        """Create mock routing service."""
        return AsyncMock()

    @pytest.fixture
    def mock_rabbitmq_service(self):
        """Create mock RabbitMQ service."""
        return AsyncMock()

    @pytest.fixture
    def mock_webhook_logging_service(self):
        """Create mock webhook logging service."""
        return AsyncMock()

    @pytest.fixture
    def process_webhook_use_case(
        self,
        mock_instagram_service,
        mock_routing_service,
        mock_rabbitmq_service,
        mock_webhook_logging_service,
    ):
        """Create ProcessWebhookUseCase instance."""
        return ProcessWebhookUseCase(
            instagram_service=mock_instagram_service,
            routing_service=mock_routing_service,
            rabbitmq_service=mock_rabbitmq_service,
            webhook_logging_service=mock_webhook_logging_service,
        )

    @pytest.fixture
    def sample_webhook_payload(self):
        """Sample webhook payload."""
        return WebhookPayload(
            object="instagram",
            entry=[
                {
                    "id": str(uuid4()),
                    "time": 1640995200,
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": str(uuid4()),
                                "text": "Test comment",
                                "media_id": "test_media_id",
                                "from": {
                                    "id": "test_user_id",
                                    "username": "test_user",
                                },
                                "created_time": "2024-01-01T00:00:00Z",
                            },
                        }
                    ],
                }
            ],
        )

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        process_webhook_use_case,
        sample_webhook_payload,
        mock_instagram_service,
        mock_routing_service,
        mock_rabbitmq_service,
        mock_webhook_logging_service,
    ):
        """Test successful webhook processing."""
        webhook_id = str(uuid4())

        # Mock Instagram service
        mock_instagram_service.extract_media_ids.return_value = ["test_media_id"]
        mock_instagram_service.get_media_info.return_value = {
            "id": "test_media_id",
            "owner": {"id": "test_owner_id"},
        }
        mock_instagram_service.extract_owner_id.return_value = "test_owner_id"

        # Mock routing service
        mock_routing_service.route_webhook.return_value = RoutingResponse(
            status="success",
            message="Webhook routed successfully",
            routed_to="test_queue",
            processing_time_ms=150,
            error_details=None,
        )

        # Mock RabbitMQ service
        mock_rabbitmq_service.publish_message.return_value = True

        result = await process_webhook_use_case.execute(
            sample_webhook_payload, webhook_id
        )

        assert result.status == "success"
        assert result.message == "Webhook routed successfully"
        assert result.routed_to == "test_queue"
        assert result.processing_time_ms > 0

        # Verify service calls
        mock_instagram_service.extract_media_ids.assert_called_once()
        mock_instagram_service.get_media_info.assert_called_once()
        mock_instagram_service.extract_owner_id.assert_called_once()
        mock_routing_service.route_webhook.assert_called_once()
        mock_rabbitmq_service.publish_message.assert_called_once()
        mock_webhook_logging_service.log_webhook_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_no_media_ids(
        self,
        process_webhook_use_case,
        sample_webhook_payload,
        mock_instagram_service,
        mock_webhook_logging_service,
    ):
        """Test webhook processing with no media IDs."""
        webhook_id = str(uuid4())

        # Mock Instagram service to return no media IDs
        mock_instagram_service.extract_media_ids.return_value = []

        result = await process_webhook_use_case.execute(
            sample_webhook_payload, webhook_id
        )

        assert result.status == "failed"
        assert "No media IDs found" in result.error_details

        # Verify logging was called
        mock_webhook_logging_service.log_webhook_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_instagram_api_error(
        self,
        process_webhook_use_case,
        sample_webhook_payload,
        mock_instagram_service,
        mock_webhook_logging_service,
    ):
        """Test webhook processing with Instagram API error."""
        webhook_id = str(uuid4())

        # Mock Instagram service to raise an error
        mock_instagram_service.extract_media_ids.return_value = ["test_media_id"]
        mock_instagram_service.get_media_info.side_effect = Exception(
            "Instagram API error"
        )

        result = await process_webhook_use_case.execute(
            sample_webhook_payload, webhook_id
        )

        assert result.status == "failed"
        assert "Instagram API error" in result.error_details

        # Verify logging was called
        mock_webhook_logging_service.log_webhook_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_routing_error(
        self,
        process_webhook_use_case,
        sample_webhook_payload,
        mock_instagram_service,
        mock_routing_service,
        mock_webhook_logging_service,
    ):
        """Test webhook processing with routing error."""
        webhook_id = str(uuid4())

        # Mock Instagram service
        mock_instagram_service.extract_media_ids.return_value = ["test_media_id"]
        mock_instagram_service.get_media_info.return_value = {
            "id": "test_media_id",
            "owner": {"id": "test_owner_id"},
        }
        mock_instagram_service.extract_owner_id.return_value = "test_owner_id"

        # Mock routing service to return error
        mock_routing_service.route_webhook.return_value = RoutingResponse(
            status="failed",
            message="Routing failed",
            routed_to=None,
            processing_time_ms=100,
            error_details="No worker app found",
        )

        result = await process_webhook_use_case.execute(
            sample_webhook_payload, webhook_id
        )

        assert result.status == "failed"
        assert "No worker app found" in result.error_details

        # Verify logging was called
        mock_webhook_logging_service.log_webhook_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_rabbitmq_error(
        self,
        process_webhook_use_case,
        sample_webhook_payload,
        mock_instagram_service,
        mock_routing_service,
        mock_rabbitmq_service,
        mock_webhook_logging_service,
    ):
        """Test webhook processing with RabbitMQ error."""
        webhook_id = str(uuid4())

        # Mock Instagram service
        mock_instagram_service.extract_media_ids.return_value = ["test_media_id"]
        mock_instagram_service.get_media_info.return_value = {
            "id": "test_media_id",
            "owner": {"id": "test_owner_id"},
        }
        mock_instagram_service.extract_owner_id.return_value = "test_owner_id"

        # Mock routing service
        mock_routing_service.route_webhook.return_value = RoutingResponse(
            status="success",
            message="Webhook routed successfully",
            routed_to="test_queue",
            processing_time_ms=150,
            error_details=None,
        )

        # Mock RabbitMQ service to fail
        mock_rabbitmq_service.publish_message.return_value = False

        result = await process_webhook_use_case.execute(
            sample_webhook_payload, webhook_id
        )

        assert result.status == "failed"
        assert "Failed to publish message" in result.error_details

        # Verify logging was called
        mock_webhook_logging_service.log_webhook_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_multiple_media_ids(
        self,
        process_webhook_use_case,
        sample_webhook_payload,
        mock_instagram_service,
        mock_routing_service,
        mock_rabbitmq_service,
        mock_webhook_logging_service,
    ):
        """Test webhook processing with multiple media IDs."""
        webhook_id = str(uuid4())

        # Mock Instagram service for multiple media IDs
        mock_instagram_service.extract_media_ids.return_value = ["media_1", "media_2"]
        mock_instagram_service.get_media_info.side_effect = [
            {"id": "media_1", "owner": {"id": "owner_1"}},
            {"id": "media_2", "owner": {"id": "owner_2"}},
        ]
        mock_instagram_service.extract_owner_id.side_effect = ["owner_1", "owner_2"]

        # Mock routing service
        mock_routing_service.route_webhook.return_value = RoutingResponse(
            status="success",
            message="Webhook routed successfully",
            routed_to="test_queue",
            processing_time_ms=150,
            error_details=None,
        )

        # Mock RabbitMQ service
        mock_rabbitmq_service.publish_message.return_value = True

        result = await process_webhook_use_case.execute(
            sample_webhook_payload, webhook_id
        )

        assert result.status == "success"

        # Verify Instagram service was called for each media ID
        assert mock_instagram_service.get_media_info.call_count == 2
        assert mock_instagram_service.extract_owner_id.call_count == 2

        # Verify routing service was called for each owner ID
        assert mock_routing_service.route_webhook.call_count == 2

        # Verify RabbitMQ service was called for each routing
        assert mock_rabbitmq_service.publish_message.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_logging_error(
        self,
        process_webhook_use_case,
        sample_webhook_payload,
        mock_instagram_service,
        mock_routing_service,
        mock_rabbitmq_service,
        mock_webhook_logging_service,
    ):
        """Test webhook processing with logging error."""
        webhook_id = str(uuid4())

        # Mock Instagram service
        mock_instagram_service.extract_media_ids.return_value = ["test_media_id"]
        mock_instagram_service.get_media_info.return_value = {
            "id": "test_media_id",
            "owner": {"id": "test_owner_id"},
        }
        mock_instagram_service.extract_owner_id.return_value = "test_owner_id"

        # Mock routing service
        mock_routing_service.route_webhook.return_value = RoutingResponse(
            status="success",
            message="Webhook routed successfully",
            routed_to="test_queue",
            processing_time_ms=150,
            error_details=None,
        )

        # Mock RabbitMQ service
        mock_rabbitmq_service.publish_message.return_value = True

        # Mock logging service to fail
        mock_webhook_logging_service.log_webhook_processing.side_effect = Exception(
            "Logging error"
        )

        # Should not raise exception, just log the error
        result = await process_webhook_use_case.execute(
            sample_webhook_payload, webhook_id
        )

        assert result.status == "success"
        # The use case should handle logging errors gracefully
