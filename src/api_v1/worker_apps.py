"""Worker app management endpoints."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api_v1.schemas import (
    WorkerAppCreate,
    WorkerAppUpdate,
    WorkerAppResponse,
    WorkerAppListResponse,
)
from src.core.dependencies import get_session
from src.core.models.worker_app import WorkerApp
from src.core.repositories.worker_app_repository import WorkerAppRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/worker-apps", tags=["worker-apps"])


@router.post("", response_model=WorkerAppResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=WorkerAppResponse, status_code=status.HTTP_201_CREATED)
async def create_worker_app(
    worker_app_data: WorkerAppCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new worker app configuration.

    Args:
        worker_app_data: Worker app creation data

    Returns:
        Created worker app

    Raises:
        409: If worker app with owner_id already exists
    """
    repo = WorkerAppRepository(session)

    # Check if worker app already exists for this owner
    if await repo.exists_by_owner_id(worker_app_data.owner_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Worker app already exists for owner_id: {worker_app_data.owner_id}"
        )

    # Create worker app
    worker_app = WorkerApp(
        owner_id=worker_app_data.owner_id,
        app_name=worker_app_data.app_name,
        base_url=str(worker_app_data.base_url),
        webhook_path=worker_app_data.webhook_path,
        queue_name=worker_app_data.queue_name,
        is_active=worker_app_data.is_active,
    )

    await repo.create(worker_app)
    await session.commit()
    await session.refresh(worker_app)

    logger.info(f"Created worker app: id={worker_app.id}, owner_id={worker_app.owner_id}")

    return worker_app


@router.get("", response_model=WorkerAppListResponse)
@router.get("/", response_model=WorkerAppListResponse)
async def list_worker_apps(
    session: Annotated[AsyncSession, Depends(get_session)],
    page: int = 1,
    size: int = 50,
    active_only: bool = False,
):
    """
    List all worker apps with pagination.

    Args:
        page: Page number (1-indexed)
        size: Page size
        active_only: If True, only return active worker apps

    Returns:
        Paginated list of worker apps
    """
    repo = WorkerAppRepository(session)

    offset = (page - 1) * size

    if active_only:
        items = await repo.get_all_active(limit=size, offset=offset)
    else:
        items = await repo.get_all(limit=size, offset=offset)

    # For simplicity, we're not implementing total count here
    # In production, you'd want to add a count query
    total = len(items)

    return WorkerAppListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
    )


@router.get("/{worker_app_id}", response_model=WorkerAppResponse)
async def get_worker_app(
    worker_app_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a specific worker app by ID.

    Args:
        worker_app_id: Worker app UUID

    Returns:
        Worker app details

    Raises:
        404: If worker app not found
    """
    repo = WorkerAppRepository(session)

    worker_app = await repo.get_by_id(worker_app_id)

    if not worker_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker app not found: {worker_app_id}"
        )

    return worker_app


@router.put("/{worker_app_id}", response_model=WorkerAppResponse)
async def update_worker_app(
    worker_app_id: UUID,
    worker_app_data: WorkerAppUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a worker app configuration.

    Args:
        worker_app_id: Worker app UUID
        worker_app_data: Worker app update data

    Returns:
        Updated worker app

    Raises:
        404: If worker app not found
    """
    repo = WorkerAppRepository(session)

    worker_app = await repo.get_by_id(worker_app_id)

    if not worker_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker app not found: {worker_app_id}"
        )

    # Update fields if provided
    if worker_app_data.app_name is not None:
        worker_app.app_name = worker_app_data.app_name

    if worker_app_data.base_url is not None:
        worker_app.base_url = str(worker_app_data.base_url)

    if worker_app_data.webhook_path is not None:
        worker_app.webhook_path = worker_app_data.webhook_path

    if worker_app_data.queue_name is not None:
        worker_app.queue_name = worker_app_data.queue_name

    if worker_app_data.is_active is not None:
        worker_app.is_active = worker_app_data.is_active

    await session.commit()
    await session.refresh(worker_app)

    logger.info(f"Updated worker app: id={worker_app_id}")

    return worker_app


@router.delete("/{worker_app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_worker_app(
    worker_app_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Delete a worker app.

    Args:
        worker_app_id: Worker app UUID

    Raises:
        404: If worker app not found
    """
    repo = WorkerAppRepository(session)

    worker_app = await repo.get_by_id(worker_app_id)

    if not worker_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker app not found: {worker_app_id}"
        )

    await repo.delete(worker_app)
    await session.commit()

    logger.info(f"Deleted worker app: id={worker_app_id}")

    return None


@router.post("/{worker_app_id}/toggle", response_model=WorkerAppResponse)
async def toggle_worker_app(
    worker_app_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Toggle the is_active status of a worker app.

    Args:
        worker_app_id: Worker app UUID

    Returns:
        Updated worker app

    Raises:
        404: If worker app not found
    """
    repo = WorkerAppRepository(session)

    worker_app = await repo.toggle_active(worker_app_id)

    if not worker_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker app not found: {worker_app_id}"
        )

    await session.commit()
    await session.refresh(worker_app)

    logger.info(f"Toggled worker app: id={worker_app_id}, is_active={worker_app.is_active}")

    return worker_app


@router.get("/owner/{owner_id}", response_model=WorkerAppResponse)
async def get_worker_app_by_owner(
    owner_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get worker app by Instagram owner ID.

    Args:
        owner_id: Instagram account ID

    Returns:
        Worker app for the owner

    Raises:
        404: If no worker app found for owner
    """
    repo = WorkerAppRepository(session)

    worker_app = await repo.get_by_owner_id(owner_id)

    if not worker_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No worker app found for owner_id: {owner_id}"
        )

    return worker_app
