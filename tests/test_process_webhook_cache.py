from typing import Any, Dict, Optional

import pytest

from src.core.models.worker_app import WorkerApp
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
    worker_app = WorkerApp(
        account_id="acct-cache-test",
        owner_instagram_username="cache-user",
        base_url="https://worker-cache.example/api",
    )
    db_session.add(worker_app)
    await db_session.commit()

    redis_cache = _FakeRedisCache()
    use_case = ProcessWebhookUseCase(
        session=db_session,
        forward_webhook_uc=_DummyForwardWebhookUseCase(),
        redis_cache=redis_cache,
    )

    # First lookup: should miss cache, fetch from DB, then populate cache.
    worker_from_db = await use_case._get_worker_app_cached(worker_app.account_id)
    assert worker_from_db is not None
    assert worker_from_db.id == worker_app.id
    assert redis_cache.get_calls == [worker_app.account_id]
    assert redis_cache.set_calls[0][0] == worker_app.account_id

    # Second lookup: should hit cache and avoid re-populating.
    worker_from_cache = await use_case._get_worker_app_cached(worker_app.account_id)
    assert worker_from_cache is not None
    assert worker_from_cache.id == worker_app.id
    assert redis_cache.get_calls == [worker_app.account_id, worker_app.account_id]
    assert len(redis_cache.set_calls) == 1
