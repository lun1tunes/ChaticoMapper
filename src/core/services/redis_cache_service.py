"""Redis cache service for fast media-to-owner lookups."""

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis_async
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class RedisCacheService:
    """
    Redis cache service for storing media_id -> owner_id mappings.

    Provides fast lookups to avoid repeated database queries and Instagram API calls.
    """

    def __init__(
        self,
        redis_url: str,
        default_ttl: int = 86400,  # 24 hours
    ):
        """
        Initialize Redis cache service.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
            default_ttl: Default TTL in seconds for cached items
        """
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self._client: Optional[Redis] = None

    async def connect(self) -> None:
        """Establish connection to Redis."""
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

    async def get_client(self) -> Redis:
        """Get Redis client, connecting if necessary."""
        if self._client is None:
            await self.connect()
        return self._client

    # Media owner caching methods
    async def get_media_owner(self, media_id: str) -> Optional[str]:
        """
        Get owner_id for a media_id from cache.

        Args:
            media_id: Instagram media ID

        Returns:
            owner_id if found in cache, None otherwise
        """
        try:
            client = await self.get_client()
            key = self._media_key(media_id)
            owner_id = await client.get(key)

            if owner_id:
                logger.debug(f"Cache HIT: media_id={media_id} -> owner_id={owner_id}")
                return owner_id
            else:
                logger.debug(f"Cache MISS: media_id={media_id}")
                return None

        except RedisError as e:
            logger.warning(f"Redis error getting media owner: {e}")
            return None

    async def set_media_owner(
        self,
        media_id: str,
        owner_id: str,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache media_id -> owner_id mapping.

        Args:
            media_id: Instagram media ID
            owner_id: Instagram account ID
            ttl: Time to live in seconds (uses default_ttl if None)

        Returns:
            True if successfully cached, False otherwise
        """
        try:
            client = await self.get_client()
            key = self._media_key(media_id)
            ttl = ttl or self.default_ttl

            await client.set(key, owner_id, ex=ttl)
            logger.debug(f"Cached: media_id={media_id} -> owner_id={owner_id} (TTL={ttl}s)")
            return True

        except RedisError as e:
            logger.warning(f"Redis error setting media owner: {e}")
            return False

    async def delete_media_owner(self, media_id: str) -> bool:
        """
        Delete media owner cache entry.

        Args:
            media_id: Instagram media ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            client = await self.get_client()
            key = self._media_key(media_id)
            result = await client.delete(key)

            if result > 0:
                logger.debug(f"Deleted cache: media_id={media_id}")
                return True
            return False

        except RedisError as e:
            logger.warning(f"Redis error deleting media owner: {e}")
            return False

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
            key = self._worker_app_key(owner_id)
            data = await client.get(key)

            if data:
                logger.debug(f"Cache HIT: worker_app for owner_id={owner_id}")
                return json.loads(data)
            else:
                logger.debug(f"Cache MISS: worker_app for owner_id={owner_id}")
                return None

        except (RedisError, json.JSONDecodeError) as e:
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
            key = self._worker_app_key(owner_id)
            ttl = ttl or self.default_ttl

            await client.set(key, json.dumps(worker_app_data), ex=ttl)
            logger.debug(f"Cached worker_app for owner_id={owner_id} (TTL={ttl}s)")
            return True

        except (RedisError, json.JSONEncodeError) as e:
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
            return await client.get(key)
        except RedisError as e:
            logger.warning(f"Redis error on get({key}): {e}")
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Generic set operation."""
        try:
            client = await self.get_client()
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
            result = await client.delete(key)
            return result > 0
        except RedisError as e:
            logger.warning(f"Redis error on delete({key}): {e}")
            return False

    async def ping(self) -> bool:
        """Check if Redis is reachable."""
        try:
            client = await self.get_client()
            await client.ping()
            return True
        except RedisError:
            return False

    # Key generation helpers
    @staticmethod
    def _media_key(media_id: str) -> str:
        """Generate Redis key for media owner mapping."""
        return f"media:{media_id}:owner"

    @staticmethod
    def _worker_app_key(owner_id: str) -> str:
        """Generate Redis key for worker app configuration."""
        return f"worker_app:{owner_id}"
