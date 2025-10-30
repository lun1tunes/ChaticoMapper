"""User management endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status

from src.api_v1.schemas import UserCreate, UserResponse
from src.core.dependencies import get_current_active_user, get_user_repository
from src.core.models.user import User
from src.core.repositories.user_repository import UserRepository
from src.core.services.security import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserCreate, repo: UserRepository = Depends(get_user_repository)) -> User:
    existing = await repo.get_by_email(user_in.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
    )
    await repo.create(user)
    await repo.session.commit()
    await repo.session.refresh(user)

    logger.info("Created user %s", user.email)
    return user


@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: Annotated[User, Security(get_current_active_user, scopes=["me"])]
) -> User:
    return current_user


@router.get("/me/items", tags=["users"])
async def read_users_me_items(
    current_user: Annotated[User, Security(get_current_active_user, scopes=["items"])]
) -> list[dict[str, str]]:
    return [
        {
            "item_id": "own-item",
            "owner": current_user.email,
        }
    ]
