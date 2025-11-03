import pytest

from src.core.models.user import User, UserRole
from src.core.services.security import hash_password


async def _create_user(session, *, email: str, password: str, role: UserRole) -> None:
    user = User(
        email=email,
        full_name="Test User",
        hashed_password=hash_password(password),
        role=role.value,
    )
    session.add(user)
    await session.commit()


async def _get_token(client, *, username: str, password: str) -> str:
    response = await client.post(
        "/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_list_worker_apps_returns_empty_for_admin(client, db_session):
    email = "admin@example.com"
    password = "test-password"
    await _create_user(db_session, email=email, password=password, role=UserRole.ADMIN)

    token = await _get_token(client, username=email, password=password)

    response = await client.get(
        "/api/v1/worker-apps",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0


@pytest.mark.asyncio
async def test_list_worker_apps_requires_admin_role(client, db_session):
    email = "basic@example.com"
    password = "test-password"
    await _create_user(db_session, email=email, password=password, role=UserRole.BASIC)

    token = await _get_token(client, username=email, password=password)

    response = await client.get(
        "/api/v1/worker-apps",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
