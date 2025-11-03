import pytest

from src.core.models.user import User, UserRole
from src.core.models.worker_app import WorkerApp
from src.core.services.security import hash_password


@pytest.mark.asyncio
async def test_token_includes_worker_app_base_url(client, db_session):
    password = "test-password"
    user = User(
        email="owner@example.com",
        full_name="Owner User",
        hashed_password=hash_password(password),
        role=UserRole.ADMIN.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    worker_app = WorkerApp(
        account_id="acct-auth-test",
        owner_instagram_username="owneruser",
        base_url="https://worker.example",
        webhook_url="https://worker.example/webhook",
        user_id=user.id,
    )

    db_session.add(worker_app)
    await db_session.commit()

    response = await client.post(
        "/token",
        data={"username": user.email, "password": password},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["base_url"] == worker_app.base_url
    assert "access_token" in payload
