import pytest
from sqlalchemy import delete

from src.core.models.user import User, UserRole
from src.core.models.worker_app import WorkerApp
from src.core.services.security import hash_password


async def _create_user(session, *, username: str, password: str, role: UserRole) -> User:
    user = User(
        username=username,
        full_name="Test User",
        hashed_password=hash_password(password),
        role=role.value,
    )
    session.add(user)
    await session.commit()
    return user


async def _get_token(client, *, username: str, password: str) -> str:
    response = await client.post(
        "/token",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


async def _create_worker_app_record(session, *, user_id, name: str) -> WorkerApp:
    worker = WorkerApp(
        base_url=f"https://{name}.example/base",
        webhook_url=f"https://{name}.example/webhook",
        user_id=user_id,
    )
    session.add(worker)
    await session.commit()
    await session.refresh(worker)
    return worker


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_worker_apps_returns_empty_for_admin(client, db_session):
    await db_session.execute(delete(WorkerApp))
    await db_session.commit()

    username = "admin_user"
    password = "test-password"
    await _create_user(db_session, username=username, password=password, role=UserRole.ADMIN)

    token = await _get_token(client, username=username, password=password)

    response = await client.get(
        "/api/v1/worker-apps",
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total"] == 0


@pytest.mark.asyncio
async def test_list_worker_apps_requires_admin_role(client, db_session):
    username = "basic_user"
    password = "test-password"
    await _create_user(db_session, username=username, password=password, role=UserRole.BASIC)

    token = await _get_token(client, username=username, password=password)

    response = await client.get(
        "/api/v1/worker-apps",
        headers=_auth_headers(token),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_and_fetch_worker_app(client, db_session):
    admin = await _create_user(db_session, username="creator", password="secret", role=UserRole.ADMIN)
    token = await _get_token(client, username=admin.username, password="secret")

    payload = {
        "base_url": "https://worker-new.example/api",
        "webhook_url": "https://worker-new.example/hook",
        "user_id": str(admin.id),
    }

    response = await client.post(
        "/api/v1/worker-apps",
        json=payload,
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    created = response.json()
    assert created["user_id"] == str(admin.id)

    worker_id = created["id"]
    get_response = await client.get(
        f"/api/v1/worker-apps/{worker_id}",
        headers=_auth_headers(token),
    )
    assert get_response.status_code == 200
    assert get_response.json()["webhook_url"] == "https://worker-new.example/hook"


@pytest.mark.asyncio
async def test_create_worker_app_conflict_returns_409(client, db_session):
    admin = await _create_user(db_session, username="conflict-admin", password="secret", role=UserRole.ADMIN)
    token = await _get_token(client, username=admin.username, password="secret")
    await _create_worker_app_record(db_session, user_id=admin.id, name="dup-owner")

    response = await client.post(
        "/api/v1/worker-apps",
        json={
            "base_url": "https://dup.example/base",
            "webhook_url": "https://dup.example/hook",
            "user_id": str(admin.id),
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_update_worker_app_changes_fields(client, db_session):
    admin = await _create_user(db_session, username="update-admin", password="secret", role=UserRole.ADMIN)
    token = await _get_token(client, username=admin.username, password="secret")
    worker = await _create_worker_app_record(db_session, user_id=admin.id, name="old-owner")

    response = await client.put(
        f"/api/v1/worker-apps/{worker.id}",
        json={
            "base_url": "https://updated.example/base",
            "webhook_url": "https://updated.example/hook",
            "user_id": str(admin.id),
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["base_url"] == "https://updated.example/base"


@pytest.mark.asyncio
async def test_delete_worker_app_removes_entry(client, db_session):
    admin = await _create_user(db_session, username="delete-admin", password="secret", role=UserRole.ADMIN)
    token = await _get_token(client, username=admin.username, password="secret")
    worker = await _create_worker_app_record(db_session, user_id=admin.id, name="delete-owner")

    response = await client.delete(
        f"/api/v1/worker-apps/{worker.id}",
        headers=_auth_headers(token),
    )

    assert response.status_code == 204
    # ensure gone
    follow_up = await client.get(
        f"/api/v1/worker-apps/{worker.id}",
        headers=_auth_headers(token),
    )
    assert follow_up.status_code == 404


@pytest.mark.asyncio
async def test_update_worker_app_not_found_returns_404(client, db_session):
    admin = await _create_user(db_session, username="update-missing", password="secret", role=UserRole.ADMIN)
    token = await _get_token(client, username=admin.username, password="secret")

    response = await client.put(
        "/api/v1/worker-apps/00000000-0000-0000-0000-000000000000",
        json={
            "base_url": "https://missing.example/base",
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_worker_app_not_found_returns_404(client, db_session):
    admin = await _create_user(db_session, username="delete-missing", password="secret", role=UserRole.ADMIN)
    token = await _get_token(client, username=admin.username, password="secret")

    response = await client.delete(
        "/api/v1/worker-apps/00000000-0000-0000-0000-000000000000",
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_non_admin_cannot_create_worker_app(client, db_session):
    user = await _create_user(db_session, username="basic", password="secret", role=UserRole.BASIC)
    token = await _get_token(client, username=user.username, password="secret")

    response = await client.post(
        "/api/v1/worker-apps",
        json={
            "base_url": "https://unauth.example/base",
            "webhook_url": "https://unauth.example/hook",
            "user_id": str(user.id),
        },
        headers=_auth_headers(token),
    )

    assert response.status_code == 403
