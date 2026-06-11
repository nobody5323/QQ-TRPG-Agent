"""Redis 缓存客户端"""

import json
from typing import Optional, Any
from redis.asyncio import Redis as AsyncRedis, ConnectionPool

from app.config import settings


class RedisClient:
    """异步 Redis 客户端封装"""

    def __init__(self):
        self._client: Optional[AsyncRedis] = None

    async def initialize(self):
        """初始化连接池"""
        if self._client is None:
            pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=20,
                decode_responses=True,
            )
            self._client = AsyncRedis(connection_pool=pool)

    async def close(self):
        """关闭连接"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def ping(self) -> bool:
        """检查连接是否正常"""
        try:
            if self._client:
                return await self._client.ping()
            return False
        except Exception:
            return False

    async def get(self, key: str) -> Optional[str]:
        if self._client:
            return await self._client.get(key)
        return None

    async def set(self, key: str, value: str, ttl: int = 1800):
        if self._client:
            await self._client.set(key, value, ex=ttl)

    async def get_json(self, key: str) -> Optional[Any]:
        val = await self.get(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return None
        return None

    async def set_json(self, key: str, value: Any, ttl: int = 1800):
        await self.set(key, json.dumps(value, ensure_ascii=False), ttl)

    async def delete(self, key: str):
        if self._client:
            await self._client.delete(key)


redis_client = RedisClient()
