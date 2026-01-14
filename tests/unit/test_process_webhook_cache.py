from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pytest

from src.core.config import get_settings
from src.core.models.user import User
from src.core.models.worker_app import WorkerApp
from src.core.repositories.oauth_token_repository import OAuthTokenRepository
from src.core.services.oauth_token_service import OAuthTokenService
from src.core.use_cases.process_webhook_use_case import ProcessWebhookUseCase


class _DummyForwardWebhookUseCase:
    async def execute(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        raise AssertionError("Forward use case should not be called in cache test")


class _FakeRedisCache:
    def __init__(self) -> None:
        self.store: Dict[str, Dict[str, Any]] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, Dict[str, Any]]] = []

    async def get_worker_app(self, account_id: str) -> Optional[Dict[str, Any]]:
        self.get_calls.append(account_id)
        return self.store.get(account_id)

    async def set_worker_app(
        self,
        account_id: str,
        worker_app_data: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        self.set_calls.append((account_id, worker_app_data))
        self.store[account_id] = worker_app_data
        return True


@pytest.mark.asyncio
async def test_get_worker_app_cached_uses_redis(db_session):
    user = User(
        username="cache-user",
        full_name="Cache User",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    worker_app = WorkerApp(
        base_url="https://worker-cache.example",
        webhook_url="https://worker-cache.example/api",
        user_id=user.id,
    )
    db_session.add(worker_app)
    await db_session.commit()

    token_service = OAuthTokenService(
        OAuthTokenRepository(db_session),
        get_settings().oauth_encryption_key,
    )
    await token_service.store_tokens(
        provider="instagram",
        account_id="acct-cache-test",
        user_id=user.id,
        instagram_user_id="ig-scoped",
        username="cache-user",
        access_token="access-token",
        refresh_token=None,
        scope="instagram_business_basic",
        access_token_expires_at=None,
        refresh_token_expires_at=None,
    )
    await db_session.commit()

    redis_cache = _FakeRedisCache()
    use_case = ProcessWebhookUseCase(
        session=db_session,
        forward_webhook_uc=_DummyForwardWebhookUseCase(),
        redis_cache=redis_cache,
    )

    # First lookup: should miss cache, fetch from DB, then populate cache.
    worker_from_db, username_from_db = await use_case._get_worker_app_cached("acct-cache-test")
    assert worker_from_db is not None
    assert worker_from_db.id == worker_app.id
    assert username_from_db == "cache-user"
    assert redis_cache.get_calls == ["acct-cache-test"]
    assert redis_cache.set_calls[0][0] == "acct-cache-test"
    assert redis_cache.set_calls[0][1]["webhook_url"] == worker_app.webhook_url

    # Second lookup: should hit cache and avoid re-populating.
    worker_from_cache, username_from_cache = await use_case._get_worker_app_cached("acct-cache-test")
    assert worker_from_cache is not None
    assert worker_from_cache.id == worker_app.id
    assert username_from_cache == "cache-user"
    assert redis_cache.get_calls == ["acct-cache-test", "acct-cache-test"]
    assert len(redis_cache.set_calls) == 1


@pytest.mark.asyncio
async def test_execute_skips_owner_comments(db_session):
    account_id = "acct-owner"
    owner_username = "owneruser"

    use_case = ProcessWebhookUseCase(
        session=db_session,
        forward_webhook_uc=_DummyForwardWebhookUseCase(),
        redis_cache=None,
    )

    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": account_id,
                "time": int(datetime.now(tz=timezone.utc).timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "owner-comment",
                            "text": "auto-response",
                            "from": {
                                "id": account_id,
                                "username": owner_username,
                            },
                            "media": {"id": "media-1"},
                        },
                    }
                ],
            }
        ],
    }

    result = await use_case.execute(
        webhook_payload=payload,
        original_headers={"content-type": "application/json"},
        raw_payload=b"{}",
    )

    assert result["success"] is True
    assert result["comments_processed"] == 0
    assert await use_case.comment_repo.exists_by_comment_id("owner-comment") is False
