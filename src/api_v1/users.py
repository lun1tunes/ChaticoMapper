"""User profile endpoints for authenticated users."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api_v1.schemas import UserResponse
from src.core.dependencies import get_current_active_user
from src.core.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> User:
    return current_user


@router.get("/me/items")
async def read_users_me_items(
    current_user: Annotated[User, Depends(get_current_active_user)]
) -> list[dict[str, str]]:
    return [{"item_id": "Foo", "owner": current_user.email}]
