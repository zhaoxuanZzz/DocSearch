"""Redis cache with TTL support.

Key patterns (from data-model.md):
  query:{query_hash}:{doc_ids_hash}:{mode}   TTL 5 min
  doc:status:{document_id}                   TTL 10 min
  routing:{doc_count}:{total_size_kb}:{intent_hash}  TTL 1 min
  job:{task_id}                              TTL 1 hour
  doc:meta:{document_id}                     TTL 30 min
"""

import hashlib
import json
from typing import Any

import redis.asyncio as aioredis

from src.core.config import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def cache_get(key: str) -> Any | None:
    r = get_redis()
    raw = await r.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    r = get_redis()
    await r.setex(key, ttl_seconds, json.dumps(value, default=str))


async def cache_delete(key: str) -> None:
    r = get_redis()
    await r.delete(key)


async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern. Returns count deleted."""
    r = get_redis()
    keys = await r.keys(pattern)
    if keys:
        return await r.delete(*keys)
    return 0


# ---- Typed helpers ----

def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def query_cache_key(query: str, doc_ids: list[str], mode: str) -> str:
    doc_ids_hash = _hash(",".join(sorted(str(i) for i in doc_ids)) or "all")
    return f"query:{_hash(query)}:{doc_ids_hash}:{mode}"


def doc_status_key(document_id: int) -> str:
    return f"doc:status:{document_id}"


def routing_cache_key(doc_count: int, total_size_kb: int, intent: str) -> str:
    return f"routing:{doc_count}:{total_size_kb}:{_hash(intent)}"


def job_cache_key(task_id: str) -> str:
    return f"job:{task_id}"


def doc_meta_key(document_id: int) -> str:
    return f"doc:meta:{document_id}"


# TTL constants (seconds)
TTL_QUERY = 300       # 5 minutes
TTL_DOC_STATUS = 600  # 10 minutes
TTL_ROUTING = 60      # 1 minute
TTL_JOB = 3600        # 1 hour
TTL_DOC_META = 1800   # 30 minutes


class CacheClient:
    """Thin OO wrapper around the functional cache helpers."""

    async def get(self, key: str) -> Any | None:
        return await cache_get(key)

    async def set(self, key: str, value: Any, ttl: int = TTL_QUERY) -> None:
        await cache_set(key, value, ttl)

    async def delete(self, key: str) -> None:
        await cache_delete(key)

    async def delete_pattern(self, pattern: str) -> int:
        return await cache_delete_pattern(pattern)

    # ── Key builders ──────────────────────────────────────────────────────

    def make_query_key(self, query: str, doc_ids: list[str], mode: str) -> str:
        return query_cache_key(query, doc_ids, mode)

    def make_doc_status_key(self, document_id: str) -> str:
        return doc_status_key(int(document_id))

    def make_routing_key(self, doc_count: int, total_size_kb: int, intent: str) -> str:
        return routing_cache_key(doc_count, total_size_kb, intent)

    def make_job_key(self, task_id: str) -> str:
        return job_cache_key(task_id)

    def make_doc_meta_key(self, document_id: str) -> str:
        return doc_meta_key(int(document_id))

