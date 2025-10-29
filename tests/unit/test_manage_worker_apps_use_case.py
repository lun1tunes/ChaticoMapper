"""Unit tests for ManageWorkerAppsUseCase."""

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from app.use_cases import ManageWorkerAppsUseCase
from app.schemas import WorkerAppCreate, WorkerAppUpdate


@pytest.mark.unit
class TestManageWorkerAppsUseCase:
    """Test cases for ManageWorkerAppsUseCase."""

    @pytest.fixture
    def mock_worker_app_repository(self):
        """Create mock worker app repository."""
        return AsyncMock()

    @pytest.fixture
    def manage_worker_apps_use_case(self, mock_worker_app_repository):
        """Create ManageWorkerAppsUseCase instance."""
        return ManageWorkerAppsUseCase(mock_worker_app_repository)

    @pytest.fixture
    def sample_worker_app_data(self):
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

    @pytest.fixture
    def sample_worker_app_create(self):
        """Sample worker app creation data."""
        return WorkerAppCreate(
            owner_id="test_owner_id",
            app_name="Test Worker App",
            base_url="https://test-worker.example.com",
            webhook_path="/webhook",
            queue_name="test_queue",
            is_active=True,
        )

    @pytest.fixture
    def sample_worker_app_update(self):
        """Sample worker app update data."""
        return WorkerAppUpdate(
            app_name="Updated Worker App",
            base_url="https://updated-worker.example.com",
            webhook_path="/webhook",
            queue_name="updated_queue",
            is_active=False,
        )

    @pytest.mark.asyncio
    async def test_create_worker_app_success(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_create,
        sample_worker_app_data,
    ):
        """Test successful worker app creation."""
        mock_worker_app_repository.create.return_value = sample_worker_app_data

        result = await manage_worker_apps_use_case.create_worker_app(
            sample_worker_app_create
        )

        assert result == sample_worker_app_data
        mock_worker_app_repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_worker_app_repository_error(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_create,
    ):
        """Test worker app creation with repository error."""
        mock_worker_app_repository.create.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await manage_worker_apps_use_case.create_worker_app(
                sample_worker_app_create
            )

    @pytest.mark.asyncio
    async def test_get_worker_app_success(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_data,
    ):
        """Test successful worker app retrieval."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.get_by_id.return_value = sample_worker_app_data

        result = await manage_worker_apps_use_case.get_worker_app(worker_app_id)

        assert result == sample_worker_app_data
        mock_worker_app_repository.get_by_id.assert_called_once_with(worker_app_id)

    @pytest.mark.asyncio
    async def test_get_worker_app_not_found(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test worker app retrieval when not found."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.get_by_id.return_value = None

        result = await manage_worker_apps_use_case.get_worker_app(worker_app_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_worker_app_repository_error(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test worker app retrieval with repository error."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.get_by_id.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await manage_worker_apps_use_case.get_worker_app(worker_app_id)

    @pytest.mark.asyncio
    async def test_list_worker_apps_success(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_data,
    ):
        """Test successful worker app listing."""
        mock_worker_app_repository.list.return_value = [sample_worker_app_data]

        result = await manage_worker_apps_use_case.list_worker_apps(limit=10, offset=0)

        assert result == [sample_worker_app_data]
        mock_worker_app_repository.list.assert_called_once_with(
            limit=10, offset=0, active_only=False
        )

    @pytest.mark.asyncio
    async def test_list_worker_apps_active_only(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_data,
    ):
        """Test worker app listing with active only filter."""
        mock_worker_app_repository.list.return_value = [sample_worker_app_data]

        result = await manage_worker_apps_use_case.list_worker_apps(
            limit=10, offset=0, active_only=True
        )

        assert result == [sample_worker_app_data]
        mock_worker_app_repository.list.assert_called_once_with(
            limit=10, offset=0, active_only=True
        )

    @pytest.mark.asyncio
    async def test_list_worker_apps_repository_error(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test worker app listing with repository error."""
        mock_worker_app_repository.list.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await manage_worker_apps_use_case.list_worker_apps()

    @pytest.mark.asyncio
    async def test_update_worker_app_success(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_update,
        sample_worker_app_data,
    ):
        """Test successful worker app update."""
        worker_app_id = str(uuid4())
        updated_data = {
            **sample_worker_app_data,
            **sample_worker_app_update.model_dump(),
        }
        mock_worker_app_repository.update.return_value = updated_data

        result = await manage_worker_apps_use_case.update_worker_app(
            worker_app_id, sample_worker_app_update
        )

        assert result == updated_data
        mock_worker_app_repository.update.assert_called_once_with(
            worker_app_id, sample_worker_app_update
        )

    @pytest.mark.asyncio
    async def test_update_worker_app_not_found(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_update,
    ):
        """Test worker app update when not found."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.update.return_value = None

        result = await manage_worker_apps_use_case.update_worker_app(
            worker_app_id, sample_worker_app_update
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_worker_app_repository_error(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_update,
    ):
        """Test worker app update with repository error."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.update.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await manage_worker_apps_use_case.update_worker_app(
                worker_app_id, sample_worker_app_update
            )

    @pytest.mark.asyncio
    async def test_delete_worker_app_success(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test successful worker app deletion."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.delete.return_value = True

        result = await manage_worker_apps_use_case.delete_worker_app(worker_app_id)

        assert result is True
        mock_worker_app_repository.delete.assert_called_once_with(worker_app_id)

    @pytest.mark.asyncio
    async def test_delete_worker_app_not_found(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test worker app deletion when not found."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.delete.return_value = False

        result = await manage_worker_apps_use_case.delete_worker_app(worker_app_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_worker_app_repository_error(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test worker app deletion with repository error."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.delete.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await manage_worker_apps_use_case.delete_worker_app(worker_app_id)

    @pytest.mark.asyncio
    async def test_toggle_worker_app_status_success(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_data,
    ):
        """Test successful worker app status toggle."""
        worker_app_id = str(uuid4())
        updated_data = {**sample_worker_app_data, "is_active": False}
        mock_worker_app_repository.toggle_status.return_value = updated_data

        result = await manage_worker_apps_use_case.toggle_worker_app_status(
            worker_app_id
        )

        assert result == updated_data
        mock_worker_app_repository.toggle_status.assert_called_once_with(worker_app_id)

    @pytest.mark.asyncio
    async def test_toggle_worker_app_status_not_found(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test worker app status toggle when not found."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.toggle_status.return_value = None

        result = await manage_worker_apps_use_case.toggle_worker_app_status(
            worker_app_id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_toggle_worker_app_status_repository_error(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test worker app status toggle with repository error."""
        worker_app_id = str(uuid4())
        mock_worker_app_repository.toggle_status.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match="Database error"):
            await manage_worker_apps_use_case.toggle_worker_app_status(worker_app_id)

    @pytest.mark.asyncio
    async def test_get_worker_app_by_owner_id_success(
        self,
        manage_worker_apps_use_case,
        mock_worker_app_repository,
        sample_worker_app_data,
    ):
        """Test successful worker app retrieval by owner ID."""
        owner_id = "test_owner_id"
        mock_worker_app_repository.get_by_owner_id.return_value = sample_worker_app_data

        result = await manage_worker_apps_use_case.get_worker_app_by_owner_id(owner_id)

        assert result == sample_worker_app_data
        mock_worker_app_repository.get_by_owner_id.assert_called_once_with(owner_id)

    @pytest.mark.asyncio
    async def test_get_worker_app_by_owner_id_not_found(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test worker app retrieval by owner ID when not found."""
        owner_id = "nonexistent_owner_id"
        mock_worker_app_repository.get_by_owner_id.return_value = None

        result = await manage_worker_apps_use_case.get_worker_app_by_owner_id(owner_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_worker_app_by_owner_id_repository_error(
        self, manage_worker_apps_use_case, mock_worker_app_repository
    ):
        """Test worker app retrieval by owner ID with repository error."""
        owner_id = "test_owner_id"
        mock_worker_app_repository.get_by_owner_id.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(Exception, match="Database error"):
            await manage_worker_apps_use_case.get_worker_app_by_owner_id(owner_id)
