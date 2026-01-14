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
from src.core.dependencies import get_current_admin_user, get_session, get_worker_app_repository
from src.core.models.user import User
from src.core.models.worker_app import WorkerApp
from src.core.repositories.worker_app_repository import WorkerAppRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/worker-apps", tags=["worker-apps"])


@router.post("", response_model=WorkerAppResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=WorkerAppResponse, status_code=status.HTTP_201_CREATED)
async def create_worker_app(
    worker_app_data: WorkerAppCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[WorkerAppRepository, Depends(get_worker_app_repository)],
    _admin_user: Annotated[User, Depends(get_current_admin_user)],
):
    """
    Create a new worker app configuration.

    Args:
        worker_app_data: Worker app creation data

    Returns:
        Created worker app

    Raises:
        409: If worker app for the user_id already exists
    """

    # Check if worker app already exists for this user
    if await repo.exists_by_user_id(worker_app_data.user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Worker app already exists for this user_id"
        )

    # Create worker app
    worker_app = WorkerApp(
        base_url=str(worker_app_data.base_url),
        user_id=worker_app_data.user_id,
        webhook_url=str(
            worker_app_data.webhook_url or worker_app_data.base_url
        ),
    )

    await repo.create(worker_app)
    await session.commit()
    await session.refresh(worker_app)

    logger.info(
        "Created worker app id=%s user_id=%s",
        worker_app.id,
        worker_app.user_id,
    )

    return worker_app


@router.get("", response_model=WorkerAppListResponse)
@router.get("/", response_model=WorkerAppListResponse)
async def list_worker_apps(
    _admin_user: Annotated[User, Depends(get_current_admin_user)],
    repo: Annotated[WorkerAppRepository, Depends(get_worker_app_repository)],
    page: int = 1,
    size: int = 50,
):
    """
    List all worker apps with pagination.

    Args:
        page: Page number (1-indexed)
        size: Page size
        (currently no filtering options)

    Returns:
        Paginated list of worker apps
    """

    offset = (page - 1) * size

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
    repo: Annotated[WorkerAppRepository, Depends(get_worker_app_repository)],
    _admin_user: Annotated[User, Depends(get_current_admin_user)],
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
    repo: Annotated[WorkerAppRepository, Depends(get_worker_app_repository)],
    _admin_user: Annotated[User, Depends(get_current_admin_user)],
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

    worker_app = await repo.get_by_id(worker_app_id)

    if not worker_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker app not found: {worker_app_id}"
        )

    # Update fields if provided
    if worker_app_data.base_url is not None:
        worker_app.base_url = str(worker_app_data.base_url)
    if worker_app_data.user_id is not None:
        worker_app.user_id = worker_app_data.user_id
    if worker_app_data.webhook_url is not None:
        worker_app.webhook_url = str(worker_app_data.webhook_url)

    await session.commit()
    await session.refresh(worker_app)

    logger.info("Updated worker app id=%s", worker_app_id)

    return worker_app


@router.delete("/{worker_app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_worker_app(
    worker_app_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    repo: Annotated[WorkerAppRepository, Depends(get_worker_app_repository)],
    _admin_user: Annotated[User, Depends(get_current_admin_user)],
):
    """
    Delete a worker app.

    Args:
        worker_app_id: Worker app UUID

    Raises:
        404: If worker app not found
    """

    worker_app = await repo.get_by_id(worker_app_id)

    if not worker_app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Worker app not found: {worker_app_id}"
        )

    await repo.delete(worker_app)
    await session.commit()

    logger.info("Deleted worker app id=%s", worker_app_id)

    return None
