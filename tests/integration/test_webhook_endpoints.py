"""Integration tests for webhook API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
import json
import hmac
import hashlib

from fastapi import status
from httpx import AsyncClient

from app.schemas import WebhookPayload


@pytest.mark.integration
class TestWebhookEndpoints:
    """Integration tests for webhook endpoints."""

    @pytest.fixture
    def webhook_secret(self):
        """Webhook secret for signature validation."""
        return "test_webhook_secret"

    @pytest.fixture
    def verify_token(self):
        """Verify token for webhook verification."""
        return "test_verify_token"

    def create_signature(self, payload: str, secret: str) -> str:
        """Create HMAC-SHA256 signature for webhook payload."""
        return hmac.new(
            secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    @pytest.mark.asyncio
    async def test_webhook_verification_success(
        self, client: AsyncClient, verify_token
    ):
        """Test successful webhook verification."""
        params = {
            "hub.mode": "subscribe",
            "hub.challenge": "test_challenge",
            "hub.verify_token": verify_token,
        }

        response = await client.get("/webhook/", params=params)

        assert response.status_code == status.HTTP_200_OK
        assert response.text == "test_challenge"

    @pytest.mark.asyncio
    async def test_webhook_verification_invalid_mode(
        self, client: AsyncClient, verify_token
    ):
        """Test webhook verification with invalid mode."""
        params = {
            "hub.mode": "invalid",
            "hub.challenge": "test_challenge",
            "hub.verify_token": verify_token,
        }

        response = await client.get("/webhook/", params=params)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_webhook_verification_invalid_token(self, client: AsyncClient):
        """Test webhook verification with invalid token."""
        params = {
            "hub.mode": "subscribe",
            "hub.challenge": "test_challenge",
            "hub.verify_token": "invalid_token",
        }

        response = await client.get("/webhook/", params=params)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_webhook_verification_missing_params(self, client: AsyncClient):
        """Test webhook verification with missing parameters."""
        response = await client.get("/webhook/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_process_webhook_success(
        self, client: AsyncClient, webhook_secret, sample_webhook_payload
    ):
        """Test successful webhook processing."""
        payload_json = json.dumps(sample_webhook_payload)
        signature = self.create_signature(payload_json, webhook_secret)

        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json",
        }

        with patch("app.api.get_process_webhook_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.execute.return_value = {
                "status": "success",
                "message": "Webhook processed successfully",
                "routed_to": "test_queue",
                "processing_time_ms": 150,
                "error_details": None,
            }
            mock_get_use_case.return_value = mock_use_case

            response = await client.post(
                "/webhook/", content=payload_json, headers=headers
            )

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["status"] == "success"
            assert response_data["message"] == "Webhook processed successfully"
            assert response_data["routed_to"] == "test_queue"

    @pytest.mark.asyncio
    async def test_process_webhook_invalid_signature(
        self, client: AsyncClient, sample_webhook_payload
    ):
        """Test webhook processing with invalid signature."""
        payload_json = json.dumps(sample_webhook_payload)
        invalid_signature = "invalid_signature"

        headers = {
            "X-Hub-Signature-256": f"sha256={invalid_signature}",
            "Content-Type": "application/json",
        }

        response = await client.post("/webhook/", content=payload_json, headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        response_data = response.json()
        assert "Invalid signature" in response_data["detail"]

    @pytest.mark.asyncio
    async def test_process_webhook_missing_signature(
        self, client: AsyncClient, sample_webhook_payload
    ):
        """Test webhook processing with missing signature."""
        payload_json = json.dumps(sample_webhook_payload)

        headers = {
            "Content-Type": "application/json",
        }

        response = await client.post("/webhook/", content=payload_json, headers=headers)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        response_data = response.json()
        assert "Missing signature" in response_data["detail"]

    @pytest.mark.asyncio
    async def test_process_webhook_invalid_json(
        self, client: AsyncClient, webhook_secret
    ):
        """Test webhook processing with invalid JSON."""
        invalid_json = "{ invalid json }"
        signature = self.create_signature(invalid_json, webhook_secret)

        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json",
        }

        response = await client.post("/webhook/", content=invalid_json, headers=headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_process_webhook_processing_error(
        self, client: AsyncClient, webhook_secret, sample_webhook_payload
    ):
        """Test webhook processing with processing error."""
        payload_json = json.dumps(sample_webhook_payload)
        signature = self.create_signature(payload_json, webhook_secret)

        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json",
        }

        with patch("app.api.get_process_webhook_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.execute.side_effect = Exception("Processing error")
            mock_get_use_case.return_value = mock_use_case

            response = await client.post(
                "/webhook/", content=payload_json, headers=headers
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            response_data = response.json()
            assert "Internal server error" in response_data["detail"]

    @pytest.mark.asyncio
    async def test_process_webhook_large_payload(
        self, client: AsyncClient, webhook_secret
    ):
        """Test webhook processing with large payload."""
        # Create a large payload
        large_payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": str(uuid4()),
                    "time": 1640995200,
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": str(uuid4()),
                                "text": "x" * 1000000,  # 1MB of text
                                "media_id": str(uuid4()),
                                "from": {
                                    "id": str(uuid4()),
                                    "username": "test_user",
                                },
                                "created_time": "2024-01-01T00:00:00Z",
                            },
                        }
                    ],
                }
            ],
        }

        payload_json = json.dumps(large_payload)
        signature = self.create_signature(payload_json, webhook_secret)

        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json",
        }

        response = await client.post("/webhook/", content=payload_json, headers=headers)

        # Should handle large payloads gracefully
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        ]

    @pytest.mark.asyncio
    async def test_process_webhook_empty_payload(
        self, client: AsyncClient, webhook_secret
    ):
        """Test webhook processing with empty payload."""
        empty_payload = {}
        payload_json = json.dumps(empty_payload)
        signature = self.create_signature(payload_json, webhook_secret)

        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "application/json",
        }

        response = await client.post("/webhook/", content=payload_json, headers=headers)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_process_webhook_wrong_content_type(
        self, client: AsyncClient, webhook_secret, sample_webhook_payload
    ):
        """Test webhook processing with wrong content type."""
        payload_json = json.dumps(sample_webhook_payload)
        signature = self.create_signature(payload_json, webhook_secret)

        headers = {
            "X-Hub-Signature-256": f"sha256={signature}",
            "Content-Type": "text/plain",
        }

        response = await client.post("/webhook/", content=payload_json, headers=headers)

        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
