import pytest

from src.core.models.user import User, UserRole
from src.core.models.worker_app import WorkerApp
from src.core.services.security import hash_password


async def _create_user(db_session, *, username: str, password: str, role: UserRole) -> User:
    user = User(
        username=username,
        full_name=f"{username.title()}",
        hashed_password=hash_password(password),
        role=role.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_worker_app(
    db_session,
    *,
    account_id: str,
    username: str,
    user_id=None,
) -> WorkerApp:
    worker_app = WorkerApp(
        account_id=account_id,
        owner_instagram_username=username,
        base_url=f"https://{username}.example/base",
        webhook_url=f"https://{username}.example/webhook",
        user_id=user_id,
    )
    db_session.add(worker_app)
    await db_session.commit()
    return worker_app


@pytest.mark.asyncio
async def test_token_includes_worker_app_base_url(client, db_session):
    password = "test-password"
    user = await _create_user(db_session, username="owner_user", password=password, role=UserRole.ADMIN)
    worker_app = await _create_worker_app(
        db_session,
        account_id="acct-auth-test",
        username="owneruser",
        user_id=user.id,
    )

    response = await client.post(
        "/token",
        data={"username": user.username, "password": password},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["base_url"] == worker_app.base_url
    assert "access_token" in payload
    # Admin scope should be present for admin users
    assert "admin" in payload["scopes"]


@pytest.mark.asyncio
async def test_token_returns_none_when_no_worker_app(client, db_session):
    password = "test-password"
    user = await _create_user(db_session, username="orphan_user", password=password, role=UserRole.BASIC)

    response = await client.post(
        "/token",
        data={"username": user.username, "password": password},
    )

    assert response.status_code == 200
    assert response.json()["base_url"] is None


@pytest.mark.asyncio
async def test_token_falls_back_to_account_lookup(client, db_session):
    password = "test-password"
    user = await _create_user(db_session, username="acct-fallback", password=password, role=UserRole.ADMIN)
    worker_app = await _create_worker_app(
        db_session,
        account_id=user.username,
        username="owner-fallback",
        user_id=None,
    )

    response = await client.post(
        "/token",
        data={"username": user.username, "password": password},
    )

    assert response.status_code == 200
    assert response.json()["base_url"] == worker_app.base_url


@pytest.mark.asyncio
async def test_token_rejects_invalid_credentials(client, db_session):
    password = "test-password"
    user = await _create_user(db_session, username="login_user", password=password, role=UserRole.BASIC)
    await _create_worker_app(db_session, account_id="acct-login", username="login-owner", user_id=user.id)

    response = await client.post(
        "/token",
        data={"username": user.username, "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"
