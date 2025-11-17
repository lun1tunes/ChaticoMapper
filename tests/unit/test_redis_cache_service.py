import pytest
from redis.exceptions import RedisError

from src.core.services import redis_cache_service
from src.core.services.redis_cache_service import RedisCacheService


class _FakeRedisClient:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.closed = False

    async def ping(self) -> None:  # pragma: no cover - trivial
        return None

    async def close(self) -> None:
        self.closed = True

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0


@pytest.mark.asyncio
async def test_worker_app_cache_happy_path(monkeypatch):
    fake_client = _FakeRedisClient()

    async def fake_from_url(*args, **kwargs):
        return fake_client

    monkeypatch.setattr(redis_cache_service.redis_async, "from_url", fake_from_url)

    service = RedisCacheService(redis_url="redis://example")
    await service.connect()

    payload = {"id": "123", "account_id": "acct", "base_url": "https://worker"}
    assert await service.set_worker_app("acct", payload) is True
    cached = await service.get_worker_app("acct")
    assert cached == payload
    assert await service.delete_worker_app("acct") is True

    await service.disconnect()
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_worker_app_cache_gracefully_handles_redis_errors(monkeypatch):
    class _ErrorRedis:
        async def get(self, key: str):
            raise RedisError("boom")

        async def set(self, key: str, value: str, ex: int | None = None):
            raise RedisError("boom")

    service = RedisCacheService(redis_url="redis://example")

    async def fake_get_client():
        return _ErrorRedis()

    monkeypatch.setattr(service, "get_client", fake_get_client)

    assert await service.get_worker_app("acct") is None
    assert await service.set_worker_app("acct", {"x": "y"}) is False
