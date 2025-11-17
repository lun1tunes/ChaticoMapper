import pytest

from src.core.models.user import User, UserRole
from src.core.repositories.user_repository import UserRepository
from src.core.services.auth_service import authenticate_user
from src.core.services.security import hash_password


@pytest.mark.asyncio
async def test_authenticate_user_success(db_session):
    repo = UserRepository(db_session)
    user = User(
        username="auth-user",
        full_name="Auth User",
        hashed_password=hash_password("super-secret"),
        role=UserRole.BASIC.value,
    )
    db_session.add(user)
    await db_session.commit()

    authenticated = await authenticate_user("auth-user", "super-secret", repo)
    assert authenticated is not None
    assert authenticated.username == "auth-user"


@pytest.mark.asyncio
async def test_authenticate_user_invalid_password(db_session):
    repo = UserRepository(db_session)
    user = User(
        username="auth-invalid",
        full_name="Auth Invalid",
        hashed_password=hash_password("correct-password"),
        role=UserRole.BASIC.value,
    )
    db_session.add(user)
    await db_session.commit()

    assert await authenticate_user("auth-invalid", "wrong-password", repo) is None


@pytest.mark.asyncio
async def test_authenticate_user_missing_user(db_session):
    repo = UserRepository(db_session)
    assert await authenticate_user("missing-user", "whatever", repo) is None
