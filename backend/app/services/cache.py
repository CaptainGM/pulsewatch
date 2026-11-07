import asyncio
import json
import logging
import time
from typing import Any

from redis import asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_RELEASE_LOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class Cache:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._memory: dict[str, tuple[float, str]] = {}
        self._memory_lock = asyncio.Lock()

    @property
    def redis(self) -> aioredis.Redis | None:
        return self._redis

    async def connect(self) -> None:
        if not settings.redis_url:
            logger.info("REDIS_URL is empty, using in-memory cache")
            return
        try:
            client = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=3,
            )
            await client.ping()
            self._redis = client
            logger.info("Connected to Redis")
        except Exception as exc:
            logger.warning("Redis unavailable (%s); falling back to memory cache", exc)
            self._redis = None

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def ping(self) -> str:
        if self._redis is None:
            return "memory"
        try:
            await self._redis.ping()
            return "ok"
        except Exception:
            return "unreachable"

    async def get_json(self, key: str) -> Any | None:
        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                return json.loads(raw) if raw else None
            except Exception as exc:
                logger.warning("Redis get failed: %s", exc)
                return None
        async with self._memory_lock:
            item = self._memory.get(key)
            if not item:
                return None
            expires_at, raw = item
            if expires_at < time.monotonic():
                self._memory.pop(key, None)
                return None
            return json.loads(raw)

    async def set_json(self, key: str, value: Any, ttl: int = 10) -> None:
        raw = json.dumps(value, default=str, ensure_ascii=False)
        if self._redis is not None:
            try:
                await self._redis.set(key, raw, ex=ttl)
                return
            except Exception as exc:
                logger.warning("Redis set failed: %s", exc)
        async with self._memory_lock:
            self._memory[key] = (time.monotonic() + ttl, raw)

    async def delete(self, *keys: str) -> None:
        if self._redis is not None:
            try:
                if keys:
                    await self._redis.delete(*keys)
                return
            except Exception as exc:
                logger.warning("Redis delete failed: %s", exc)
        async with self._memory_lock:
            for key in keys:
                self._memory.pop(key, None)

    async def delete_prefix(self, prefix: str) -> None:
        if self._redis is not None:
            try:
                async for key in self._redis.scan_iter(match=f"{prefix}*"):
                    await self._redis.delete(key)
                return
            except Exception as exc:
                logger.warning("Redis scan/delete failed: %s", exc)
        async with self._memory_lock:
            for key in [key for key in self._memory if key.startswith(prefix)]:
                self._memory.pop(key, None)

    async def publish(self, channel: str, payload: dict) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.publish(channel, json.dumps(payload, default=str, ensure_ascii=False))
        except Exception as exc:
            logger.warning("Redis publish failed: %s", exc)

    async def subscribe(self, channel: str):
        if self._redis is None:
            return None
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(channel)
            return pubsub
        except Exception as exc:
            logger.warning("Redis subscribe failed: %s", exc)
            return None

    async def acquire_lock(self, key: str, ttl: int = 120) -> str | None:
        token = f"{time.time_ns()}"
        if self._redis is None:
            return token
        try:
            acquired = await self._redis.set(key, token, nx=True, ex=ttl)
            return token if acquired else None
        except Exception as exc:
            logger.warning("Redis lock failed (%s); continuing with local lock", exc)
            return token

    async def release_lock(self, key: str, token: str | None) -> None:
        if self._redis is None or token is None:
            return
        try:
            await self._redis.eval(_RELEASE_LOCK_SCRIPT, 1, key, token)
        except Exception as exc:
            logger.warning("Redis unlock failed: %s", exc)


cache = Cache()
