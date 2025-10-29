"""Integration tests for monitoring API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import status
from httpx import AsyncClient


@pytest.mark.integration
class TestMonitoringEndpoints:
    """Integration tests for monitoring endpoints."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, client: AsyncClient):
        """Test successful health check."""
        with (
            patch("app.api.get_rabbitmq_service") as mock_get_rabbitmq,
            patch("app.api.get_database_session") as mock_get_db,
        ):

            # Mock RabbitMQ service
            mock_rabbitmq_service = AsyncMock()
            mock_rabbitmq_service.is_connected.return_value = True
            mock_get_rabbitmq.return_value = mock_rabbitmq_service

            # Mock database session
            mock_db_session = AsyncMock()
            mock_db_session.execute.return_value = None
            mock_get_db.return_value = mock_db_session

            response = await client.get("/monitoring/health")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["status"] == "healthy"
            assert "timestamp" in response_data
            assert "services" in response_data
            assert response_data["services"]["rabbitmq"] == "healthy"
            assert response_data["services"]["database"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_check_rabbitmq_unhealthy(self, client: AsyncClient):
        """Test health check with unhealthy RabbitMQ."""
        with (
            patch("app.api.get_rabbitmq_service") as mock_get_rabbitmq,
            patch("app.api.get_database_session") as mock_get_db,
        ):

            # Mock RabbitMQ service as unhealthy
            mock_rabbitmq_service = AsyncMock()
            mock_rabbitmq_service.is_connected.return_value = False
            mock_get_rabbitmq.return_value = mock_rabbitmq_service

            # Mock database session
            mock_db_session = AsyncMock()
            mock_db_session.execute.return_value = None
            mock_get_db.return_value = mock_db_session

            response = await client.get("/monitoring/health")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["status"] == "unhealthy"
            assert "unhealthy" in response_data["services"]["rabbitmq"]

    @pytest.mark.asyncio
    async def test_health_check_database_unhealthy(self, client: AsyncClient):
        """Test health check with unhealthy database."""
        with (
            patch("app.api.get_rabbitmq_service") as mock_get_rabbitmq,
            patch("app.api.get_database_session") as mock_get_db,
        ):

            # Mock RabbitMQ service
            mock_rabbitmq_service = AsyncMock()
            mock_rabbitmq_service.is_connected.return_value = True
            mock_get_rabbitmq.return_value = mock_rabbitmq_service

            # Mock database session to raise error
            mock_db_session = AsyncMock()
            mock_db_session.execute.side_effect = Exception(
                "Database connection failed"
            )
            mock_get_db.return_value = mock_db_session

            response = await client.get("/monitoring/health")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["status"] == "unhealthy"
            assert "unhealthy" in response_data["services"]["database"]

    @pytest.mark.asyncio
    async def test_health_check_all_unhealthy(self, client: AsyncClient):
        """Test health check with all services unhealthy."""
        with (
            patch("app.api.get_rabbitmq_service") as mock_get_rabbitmq,
            patch("app.api.get_database_session") as mock_get_db,
        ):

            # Mock RabbitMQ service as unhealthy
            mock_rabbitmq_service = AsyncMock()
            mock_rabbitmq_service.is_connected.return_value = False
            mock_get_rabbitmq.return_value = mock_rabbitmq_service

            # Mock database session to raise error
            mock_db_session = AsyncMock()
            mock_db_session.execute.side_effect = Exception(
                "Database connection failed"
            )
            mock_get_db.return_value = mock_db_session

            response = await client.get("/monitoring/health")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["status"] == "unhealthy"
            assert "unhealthy" in response_data["services"]["rabbitmq"]
            assert "unhealthy" in response_data["services"]["database"]

    @pytest.mark.asyncio
    async def test_get_metrics_success(self, client: AsyncClient):
        """Test successful metrics retrieval."""
        mock_webhook_stats = {
            "total": 1000,
            "success": 950,
            "failed": 50,
            "routed": 900,
        }

        mock_worker_apps = [
            {"id": str(uuid4()), "is_active": True},
            {"id": str(uuid4()), "is_active": True},
            {"id": str(uuid4()), "is_active": False},
        ]

        mock_rabbitmq_queues = {
            "test_queue": {
                "message_count": 10,
                "consumer_count": 2,
            }
        }

        with (
            patch("app.api.get_webhook_logging_use_case") as mock_get_logging,
            patch("app.api.get_manage_worker_apps_use_case") as mock_get_manage,
            patch("app.api.get_rabbitmq_service") as mock_get_rabbitmq,
        ):

            # Mock webhook logging service
            mock_logging_use_case = AsyncMock()
            mock_logging_use_case.get_webhook_stats.return_value = mock_webhook_stats
            mock_get_logging.return_value = mock_logging_use_case

            # Mock worker app management service
            mock_manage_use_case = AsyncMock()
            mock_manage_use_case.list_worker_apps.side_effect = [
                mock_worker_apps,
                mock_worker_apps[:2],
            ]
            mock_get_manage.return_value = mock_manage_use_case

            # Mock RabbitMQ service
            mock_rabbitmq_service = AsyncMock()
            mock_rabbitmq_service.get_queue_info.return_value = mock_rabbitmq_queues[
                "test_queue"
            ]
            mock_get_rabbitmq.return_value = mock_rabbitmq_service

            response = await client.get("/monitoring/metrics")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["webhook_total"] == 1000
            assert response_data["webhook_success"] == 950
            assert response_data["webhook_failed"] == 50
            assert response_data["webhook_routed"] == 900
            assert response_data["worker_apps_total"] == 3
            assert response_data["worker_apps_active"] == 2
            assert "rabbitmq_queues" in response_data

    @pytest.mark.asyncio
    async def test_get_metrics_error_handling(self, client: AsyncClient):
        """Test metrics retrieval with error handling."""
        with (
            patch("app.api.get_webhook_logging_use_case") as mock_get_logging,
            patch("app.api.get_manage_worker_apps_use_case") as mock_get_manage,
            patch("app.api.get_rabbitmq_service") as mock_get_rabbitmq,
        ):

            # Mock services to raise errors
            mock_logging_use_case = AsyncMock()
            mock_logging_use_case.get_webhook_stats.side_effect = Exception(
                "Logging error"
            )
            mock_get_logging.return_value = mock_logging_use_case

            mock_manage_use_case = AsyncMock()
            mock_manage_use_case.list_worker_apps.side_effect = Exception(
                "Management error"
            )
            mock_get_manage.return_value = mock_manage_use_case

            mock_rabbitmq_service = AsyncMock()
            mock_rabbitmq_service.get_queue_info.side_effect = Exception(
                "RabbitMQ error"
            )
            mock_get_rabbitmq.return_value = mock_rabbitmq_service

            response = await client.get("/monitoring/metrics")

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            response_data = response.json()
            assert "Internal server error" in response_data["detail"]

    @pytest.mark.asyncio
    async def test_get_webhook_logs_success(self, client: AsyncClient):
        """Test successful webhook logs retrieval."""
        mock_logs = [
            {
                "id": str(uuid4()),
                "webhook_id": str(uuid4()),
                "owner_id": "test_owner_id",
                "processing_status": "success",
                "processing_time_ms": 150,
                "created_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": str(uuid4()),
                "webhook_id": str(uuid4()),
                "owner_id": "test_owner_id_2",
                "processing_status": "failed",
                "processing_time_ms": 200,
                "error_message": "Test error",
                "created_at": "2024-01-01T01:00:00Z",
            },
        ]

        with patch("app.api.get_webhook_logging_use_case") as mock_get_logging:
            mock_logging_use_case = AsyncMock()
            mock_logging_use_case.get_webhook_logs.return_value = mock_logs
            mock_get_logging.return_value = mock_logging_use_case

            response = await client.get("/monitoring/webhook-logs")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert len(response_data["logs"]) == 2
            assert response_data["total"] == 2
            assert response_data["limit"] == 100
            assert response_data["offset"] == 0

    @pytest.mark.asyncio
    async def test_get_webhook_logs_with_filters(self, client: AsyncClient):
        """Test webhook logs retrieval with filters."""
        mock_logs = []

        with patch("app.api.get_webhook_logging_use_case") as mock_get_logging:
            mock_logging_use_case = AsyncMock()
            mock_logging_use_case.get_webhook_logs.return_value = mock_logs
            mock_get_logging.return_value = mock_logging_use_case

            response = await client.get(
                "/monitoring/webhook-logs?limit=10&offset=20&status=failed&worker_app_id=test_id"
            )

            assert response.status_code == status.HTTP_200_OK
            mock_logging_use_case.get_webhook_logs.assert_called_once_with(
                limit=10, offset=20, status="failed", worker_app_id="test_id"
            )

    @pytest.mark.asyncio
    async def test_get_webhook_logs_error_handling(self, client: AsyncClient):
        """Test webhook logs retrieval with error handling."""
        with patch("app.api.get_webhook_logging_use_case") as mock_get_logging:
            mock_logging_use_case = AsyncMock()
            mock_logging_use_case.get_webhook_logs.side_effect = Exception(
                "Logging error"
            )
            mock_get_logging.return_value = mock_logging_use_case

            response = await client.get("/monitoring/webhook-logs")

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            response_data = response.json()
            assert "Internal server error" in response_data["detail"]

    @pytest.mark.asyncio
    async def test_monitoring_endpoints_unauthorized(self, client: AsyncClient):
        """Test monitoring endpoints without proper authentication."""
        # In a real application, you might want to add authentication
        # For now, these endpoints are public, but this test shows how you'd test auth

        response = await client.get("/monitoring/health")
        assert response.status_code == status.HTTP_200_OK  # Currently public

        response = await client.get("/monitoring/metrics")
        assert response.status_code == status.HTTP_200_OK  # Currently public

        response = await client.get("/monitoring/webhook-logs")
        assert response.status_code == status.HTTP_200_OK  # Currently public

    @pytest.mark.asyncio
    async def test_monitoring_endpoints_rate_limiting(self, client: AsyncClient):
        """Test monitoring endpoints with rate limiting."""
        # This test would be relevant if rate limiting is implemented
        # For now, we'll just test that endpoints respond normally

        # Make multiple requests quickly
        for _ in range(5):
            response = await client.get("/monitoring/health")
            assert response.status_code == status.HTTP_200_OK
