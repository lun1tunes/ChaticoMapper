"""Authentication endpoints aligned with FastAPI OAuth2 password flow example."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from src.api_v1.schemas import Token
from src.core.config import get_settings
from src.core.dependencies import (
    get_current_admin_user,
    get_user_repository,
    get_worker_app_repository,
)
from src.core.models.user import User, UserRole
from src.core.repositories.user_repository import UserRepository
from src.core.repositories.worker_app_repository import WorkerAppRepository
from src.core.services.auth_service import authenticate_user
from src.core.services.security import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    worker_app_repo: Annotated[WorkerAppRepository, Depends(get_worker_app_repository)],
) -> Token:
    """
    Authenticate user credentials issued as form data and respond with a bearer token.
    """
    settings = get_settings()
    user = await authenticate_user(form_data.username, form_data.password, user_repo)
    if not user:
        logger.warning("Authentication failed for user %s", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scopes = ["me"]
    if (user.role or "").lower() == UserRole.ADMIN.value:
        scopes.append("admin")

    access_token_expires = timedelta(minutes=settings.jwt.expire_minutes)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role,
            "scopes": scopes,
        },
        expires_delta=access_token_expires,
    )

    base_url: Optional[str] = None
    worker_app = None
    if user.id:
        worker_app = await worker_app_repo.get_by_user_id(user.id)
    if not worker_app:
        worker_app = await worker_app_repo.get_by_account_id(user.username)
    if worker_app:
        base_url = worker_app.base_url

    logger.info("Issued access token for %s", user.username)
    return Token(access_token=access_token, token_type="bearer", base_url=base_url, scopes=scopes)
