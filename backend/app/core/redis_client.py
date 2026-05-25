"""Redis JSON cache helpers."""


from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings

_singleton: redis.Redis | None = None


def redis_connection() -> redis.Redis:
    global _singleton
    if _singleton is None:
        cfg = get_settings()
        url = cfg.redis_url
        _singleton = redis.from_url(url, encoding="utf-8", decode_responses=True)
    return _singleton

async def cache_save_json(bucket: str, payload: Any, ttl_seconds: int = 86400) -> None:
    redis_obj = redis_connection()
    serialized = json.dumps(payload)
    await redis_obj.set(bucket, serialized, ex=int(ttl_seconds))

async def cache_load_json(bucket: str) -> Any | None:
    redis_obj = redis_connection()
    serialized = await redis_obj.get(bucket)
    if serialized is None:
        return None
    return json.loads(serialized)
