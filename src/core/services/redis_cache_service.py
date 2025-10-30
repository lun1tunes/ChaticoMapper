"""Redis cache service for caching worker app lookups."""

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis_async
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisCacheService:
    """Redis cache service for storing webhook-related data."""

    def __init__(
        self,
        redis_url: Optional[str],
        default_ttl: int = 86400,  # 24 hours
    ):
        """
        Initialize Redis cache service.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
            default_ttl: Default TTL in seconds for cached items
        """
        self.redis_url = redis_url.strip() if redis_url else None
        self.default_ttl = default_ttl
        self._client: Optional[Redis] = None

    @property
    def is_configured(self) -> bool:
        """Check whether Redis caching is configured."""
        return bool(self.redis_url)

    async def connect(self) -> None:
        """Establish connection to Redis."""
        if not self.is_configured:
            logger.debug("Redis URL not configured; skipping connection")
            return

        if self._client is None:
            try:
                self._client = await redis_async.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._client.ping()
                logger.info("Redis connection established successfully")
            except RedisError as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    async def get_client(self) -> Optional[Redis]:
        """Get Redis client, connecting if necessary."""
        if not self.is_configured:
            return None

        if self._client is None:
            await self.connect()
        return self._client

    # Worker app caching methods
    async def get_worker_app(self, owner_id: str) -> Optional[dict]:
        """
        Get worker app configuration for an owner_id from cache.

        Args:
            owner_id: Instagram account ID

        Returns:
            Worker app data dict if found, None otherwise
        """
        try:
            client = await self.get_client()
            if client is None:
                return None

            key = self._worker_app_key(owner_id)
            data = await client.get(key)

            if data:
                logger.debug(f"Cache HIT: worker_app for owner_id={owner_id}")
                return json.loads(data)
            else:
                logger.debug(f"Cache MISS: worker_app for owner_id={owner_id}")
                return None

        except (RedisError, json.JSONDecodeError, TypeError) as e:
            logger.warning(f"Redis error getting worker app: {e}")
            return None

    async def set_worker_app(
        self,
        owner_id: str,
        worker_app_data: dict,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache worker app configuration.

        Args:
            owner_id: Instagram account ID
            worker_app_data: Worker app configuration dict
            ttl: Time to live in seconds (uses default_ttl if None)

        Returns:
            True if successfully cached, False otherwise
        """
        try:
            client = await self.get_client()
            if client is None:
                return False

            key = self._worker_app_key(owner_id)
            ttl = ttl or self.default_ttl

            await client.set(key, json.dumps(worker_app_data), ex=ttl)
            logger.debug(f"Cached worker_app for owner_id={owner_id} (TTL={ttl}s)")
            return True

        except (RedisError, TypeError, ValueError) as e:
            logger.warning(f"Redis error setting worker app: {e}")
            return False

    async def delete_worker_app(self, owner_id: str) -> bool:
        """
        Delete worker app cache entry.

        Args:
            owner_id: Instagram account ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            client = await self.get_client()
            if client is None:
                return False

            key = self._worker_app_key(owner_id)
            result = await client.delete(key)

            if result > 0:
                logger.debug(f"Deleted cache: worker_app for owner_id={owner_id}")
                return True
            return False

        except RedisError as e:
            logger.warning(f"Redis error deleting worker app: {e}")
            return False

    # Generic cache methods
    async def get(self, key: str) -> Optional[Any]:
        """Generic get operation."""
        try:
            client = await self.get_client()
            if client is None:
                return None

            return await client.get(key)
        except RedisError as e:
            logger.warning(f"Redis error on get({key}): {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Generic set operation."""
        try:
            client = await self.get_client()
            if client is None:
                return False

            ttl = ttl or self.default_ttl
            await client.set(key, value, ex=ttl)
            return True
        except RedisError as e:
            logger.warning(f"Redis error on set({key}): {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Generic delete operation."""
        try:
            client = await self.get_client()
            if client is None:
                return False

            result = await client.delete(key)
            return result > 0
        except RedisError as e:
            logger.warning(f"Redis error on delete({key}): {e}")
            return False

    async def ping(self) -> bool:
        """Check if Redis is reachable."""
        try:
            client = await self.get_client()
            if client is None:
                return False

            await client.ping()
            return True
        except RedisError:
            return False

    # Key generation helpers
    @staticmethod
    def _worker_app_key(owner_id: str) -> str:
        """Generate Redis key for worker app configuration."""
        return f"worker_app:{owner_id}"
