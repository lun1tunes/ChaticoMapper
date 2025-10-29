"""Integration tests for worker app management API endpoints."""

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi import status
from httpx import AsyncClient

from app.schemas import WorkerAppCreate, WorkerAppUpdate


@pytest.mark.integration
class TestWorkerAppEndpoints:
    """Integration tests for worker app management endpoints."""

    @pytest.fixture
    def sample_worker_app_data(self):
        """Sample worker app data."""
        return {
            "owner_id": "test_owner_id",
            "app_name": "Test Worker App",
            "base_url": "https://test-worker.example.com",
            "webhook_path": "/webhook",
            "queue_name": "test_queue",
            "is_active": True,
        }

    @pytest.fixture
    def sample_worker_app_response(self):
        """Sample worker app response."""
        return {
            "id": str(uuid4()),
            "owner_id": "test_owner_id",
            "app_name": "Test Worker App",
            "base_url": "https://test-worker.example.com",
            "webhook_path": "/webhook",
            "queue_name": "test_queue",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }

    @pytest.mark.asyncio
    async def test_create_worker_app_success(
        self, client: AsyncClient, sample_worker_app_data, sample_worker_app_response
    ):
        """Test successful worker app creation."""
        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.create_worker_app.return_value = sample_worker_app_response
            mock_get_use_case.return_value = mock_use_case

            response = await client.post("/worker-apps/", json=sample_worker_app_data)

            assert response.status_code == status.HTTP_201_CREATED
            response_data = response.json()
            assert response_data["id"] == sample_worker_app_response["id"]
            assert response_data["owner_id"] == sample_worker_app_data["owner_id"]
            assert response_data["app_name"] == sample_worker_app_data["app_name"]
            assert response_data["base_url"] == sample_worker_app_data["base_url"]

    @pytest.mark.asyncio
    async def test_create_worker_app_invalid_data(self, client: AsyncClient):
        """Test worker app creation with invalid data."""
        invalid_data = {
            "owner_id": "",  # Empty owner_id
            "app_name": "Test App",
            "base_url": "invalid-url",  # Invalid URL
            "webhook_path": "/webhook",
            "queue_name": "test_queue",
            "is_active": True,
        }

        response = await client.post("/worker-apps/", json=invalid_data)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_create_worker_app_missing_fields(self, client: AsyncClient):
        """Test worker app creation with missing required fields."""
        incomplete_data = {
            "app_name": "Test App",
            # Missing required fields
        }

        response = await client.post("/worker-apps/", json=incomplete_data)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_create_worker_app_duplicate_owner_id(
        self, client: AsyncClient, sample_worker_app_data
    ):
        """Test worker app creation with duplicate owner ID."""
        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.create_worker_app.side_effect = ValueError(
                "Owner ID already exists"
            )
            mock_get_use_case.return_value = mock_use_case

            response = await client.post("/worker-apps/", json=sample_worker_app_data)

            assert response.status_code == status.HTTP_400_BAD_REQUEST
            response_data = response.json()
            assert "Owner ID already exists" in response_data["detail"]

    @pytest.mark.asyncio
    async def test_get_worker_apps_success(
        self, client: AsyncClient, sample_worker_app_response
    ):
        """Test successful worker app listing."""
        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.list_worker_apps.return_value = [sample_worker_app_response]
            mock_get_use_case.return_value = mock_use_case

            response = await client.get("/worker-apps/")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert len(response_data) == 1
            assert response_data[0]["id"] == sample_worker_app_response["id"]

    @pytest.mark.asyncio
    async def test_get_worker_apps_with_pagination(
        self, client: AsyncClient, sample_worker_app_response
    ):
        """Test worker app listing with pagination."""
        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.list_worker_apps.return_value = [sample_worker_app_response]
            mock_get_use_case.return_value = mock_use_case

            response = await client.get("/worker-apps/?limit=10&offset=0")

            assert response.status_code == status.HTTP_200_OK
            mock_use_case.list_worker_apps.assert_called_once_with(
                limit=10, offset=0, active_only=False
            )

    @pytest.mark.asyncio
    async def test_get_worker_apps_active_only(
        self, client: AsyncClient, sample_worker_app_response
    ):
        """Test worker app listing with active only filter."""
        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.list_worker_apps.return_value = [sample_worker_app_response]
            mock_get_use_case.return_value = mock_use_case

            response = await client.get("/worker-apps/?active_only=true")

            assert response.status_code == status.HTTP_200_OK
            mock_use_case.list_worker_apps.assert_called_once_with(
                limit=100, offset=0, active_only=True
            )

    @pytest.mark.asyncio
    async def test_get_worker_app_by_id_success(
        self, client: AsyncClient, sample_worker_app_response
    ):
        """Test successful worker app retrieval by ID."""
        worker_app_id = sample_worker_app_response["id"]

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.get_worker_app.return_value = sample_worker_app_response
            mock_get_use_case.return_value = mock_use_case

            response = await client.get(f"/worker-apps/{worker_app_id}")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["id"] == worker_app_id

    @pytest.mark.asyncio
    async def test_get_worker_app_by_id_not_found(self, client: AsyncClient):
        """Test worker app retrieval by ID when not found."""
        worker_app_id = str(uuid4())

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.get_worker_app.return_value = None
            mock_get_use_case.return_value = mock_use_case

            response = await client.get(f"/worker-apps/{worker_app_id}")

            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_worker_app_by_owner_id_success(
        self, client: AsyncClient, sample_worker_app_response
    ):
        """Test successful worker app retrieval by owner ID."""
        owner_id = sample_worker_app_response["owner_id"]

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.get_worker_app_by_owner_id.return_value = (
                sample_worker_app_response
            )
            mock_get_use_case.return_value = mock_use_case

            response = await client.get(f"/worker-apps/by-owner/{owner_id}")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["owner_id"] == owner_id

    @pytest.mark.asyncio
    async def test_get_worker_app_by_owner_id_not_found(self, client: AsyncClient):
        """Test worker app retrieval by owner ID when not found."""
        owner_id = "nonexistent_owner_id"

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.get_worker_app_by_owner_id.return_value = None
            mock_get_use_case.return_value = mock_use_case

            response = await client.get(f"/worker-apps/by-owner/{owner_id}")

            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_worker_app_success(
        self, client: AsyncClient, sample_worker_app_response
    ):
        """Test successful worker app update."""
        worker_app_id = sample_worker_app_response["id"]
        update_data = {
            "app_name": "Updated Worker App",
            "base_url": "https://updated-worker.example.com",
            "webhook_path": "/webhook",
            "queue_name": "updated_queue",
            "is_active": False,
        }

        updated_response = {**sample_worker_app_response, **update_data}

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.update_worker_app.return_value = updated_response
            mock_get_use_case.return_value = mock_use_case

            response = await client.put(
                f"/worker-apps/{worker_app_id}", json=update_data
            )

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["app_name"] == update_data["app_name"]
            assert response_data["base_url"] == update_data["base_url"]
            assert response_data["is_active"] == update_data["is_active"]

    @pytest.mark.asyncio
    async def test_update_worker_app_not_found(self, client: AsyncClient):
        """Test worker app update when not found."""
        worker_app_id = str(uuid4())
        update_data = {
            "app_name": "Updated Worker App",
        }

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.update_worker_app.return_value = None
            mock_get_use_case.return_value = mock_use_case

            response = await client.put(
                f"/worker-apps/{worker_app_id}", json=update_data
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_update_worker_app_invalid_data(
        self, client: AsyncClient, sample_worker_app_response
    ):
        """Test worker app update with invalid data."""
        worker_app_id = sample_worker_app_response["id"]
        invalid_data = {
            "base_url": "invalid-url",  # Invalid URL
        }

        response = await client.put(f"/worker-apps/{worker_app_id}", json=invalid_data)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    @pytest.mark.asyncio
    async def test_delete_worker_app_success(
        self, client: AsyncClient, sample_worker_app_response
    ):
        """Test successful worker app deletion."""
        worker_app_id = sample_worker_app_response["id"]

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.delete_worker_app.return_value = True
            mock_get_use_case.return_value = mock_use_case

            response = await client.delete(f"/worker-apps/{worker_app_id}")

            assert response.status_code == status.HTTP_204_NO_CONTENT

    @pytest.mark.asyncio
    async def test_delete_worker_app_not_found(self, client: AsyncClient):
        """Test worker app deletion when not found."""
        worker_app_id = str(uuid4())

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.delete_worker_app.return_value = False
            mock_get_use_case.return_value = mock_use_case

            response = await client.delete(f"/worker-apps/{worker_app_id}")

            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_toggle_worker_app_status_success(
        self, client: AsyncClient, sample_worker_app_response
    ):
        """Test successful worker app status toggle."""
        worker_app_id = sample_worker_app_response["id"]
        toggled_response = {**sample_worker_app_response, "is_active": False}

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.toggle_worker_app_status.return_value = toggled_response
            mock_get_use_case.return_value = mock_use_case

            response = await client.post(f"/worker-apps/{worker_app_id}/toggle")

            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()
            assert response_data["is_active"] == False

    @pytest.mark.asyncio
    async def test_toggle_worker_app_status_not_found(self, client: AsyncClient):
        """Test worker app status toggle when not found."""
        worker_app_id = str(uuid4())

        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.toggle_worker_app_status.return_value = None
            mock_get_use_case.return_value = mock_use_case

            response = await client.post(f"/worker-apps/{worker_app_id}/toggle")

            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_worker_app_endpoints_error_handling(
        self, client: AsyncClient, sample_worker_app_data
    ):
        """Test worker app endpoints error handling."""
        with patch("app.api.get_manage_worker_apps_use_case") as mock_get_use_case:
            mock_use_case = AsyncMock()
            mock_use_case.create_worker_app.side_effect = Exception("Database error")
            mock_get_use_case.return_value = mock_use_case

            response = await client.post("/worker-apps/", json=sample_worker_app_data)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            response_data = response.json()
            assert "Internal server error" in response_data["detail"]
