"""Authentication helper functions."""

from __future__ import annotations

from src.core.models.user import User
from src.core.repositories.user_repository import UserRepository
from src.core.services.security import verify_password


async def authenticate_user(username: str, password: str, repo: UserRepository) -> User | None:
    user = await repo.get_by_username(username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user
