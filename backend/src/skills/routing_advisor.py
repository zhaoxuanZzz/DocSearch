"""T050-T053: Routing advisor service.

Implements the FR-022/023/024/025 routing decision logic:
- Small doc set → grep/read preferred
- Large doc set → query preferred
- sequential intent + query → fallback=read + low_confidence_note
"""

from __future__ import annotations

import hashlib
import json
import logging

from psycopg_pool import AsyncConnectionPool

from src.core.config import settings
from src.models.schemas import RoutingRequest, RoutingResponse
from src.storage.cache import CacheClient

logger = logging.getLogger(__name__)

_LOW_CONFIDENCE_THRESHOLD = 0.6


async def _fetch_doc_stats(
    pool: AsyncConnectionPool,
    doc_ids: list[int] | None,
) -> dict:
    """Fetch document statistics for the routing decision (mockable for tests)."""
    if doc_ids:
        where = "WHERE id = ANY(%s)"
        params: tuple = (doc_ids,)
    else:
        where = ""
        params = ()

    async with pool.connection() as conn:
        rows = await conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_docs,
                COALESCE(SUM(file_size), 0) AS total_size_bytes,
                COALESCE(SUM(chunk_count), 0) AS total_chunks,
                COUNT(*) FILTER (WHERE status = 'indexed') AS indexed_docs,
                COUNT(*) FILTER (WHERE status != 'indexed') AS unindexed_docs
            FROM documents
            {where}
            """,
            params if params else None,
        )
        row = await rows.fetchone()

    return {
        "total_docs": row[0] or 0,
        "total_size_bytes": row[1] or 0,
        "total_chunks": row[2] or 0,
        "indexed_docs": row[3] or 0,
        "unindexed_docs": row[4] or 0,
    }


async def get_routing_suggestion(
    pool: AsyncConnectionPool,
    request: RoutingRequest,
) -> RoutingResponse:
    """T050: Compute routing recommendation based on doc set size and intent."""
    cache = CacheClient()

    # Build cache key
    ids_str = ",".join(sorted(str(d) for d in (request.doc_ids or [])))
    intent_hash = hashlib.md5(
        f"{request.query_intent}:{request.query_sample or ''}".encode()
    ).hexdigest()[:8]

    # Query doc stats (extracted for mockability in tests)
    doc_id_ints = [int(d) for d in request.doc_ids] if request.doc_ids else None
    stats = await _fetch_doc_stats(pool, doc_id_ints)

    total_docs = stats["total_docs"]
    total_size_bytes = stats["total_size_bytes"]
    total_chunks = stats["total_chunks"]
    indexed_docs = stats["indexed_docs"]
    unindexed_docs = stats["unindexed_docs"]

    # T053: build cache key now that we have real stats
    total_size_kb = total_size_bytes // 1024
    routing_key = cache.make_routing_key(total_docs, total_size_kb, intent_hash)
    cached = await cache.get(routing_key)
    if cached:
        return RoutingResponse(**json.loads(cached))

    # --- Decision logic (FR-022 / FR-023) ---
    small_threshold = settings.small_doc_threshold
    small_size_mb = settings.small_size_mb
    total_size_mb = total_size_bytes / (1024 * 1024)
    is_small = total_docs <= small_threshold and total_size_mb <= small_size_mb
    intent = request.query_intent

    if is_small:
        if intent == "pattern":
            recommended = "grep"
            fallback = "query"
            confidence = 0.90
            reason = (
                f"目标文档集仅 {total_docs} 份（共 {total_size_mb:.1f}MB），低于小文档阈值"
                f"（{small_threshold} 份/{small_size_mb}MB）。查询意图为模式匹配，grep 可精准定位所有位置。"
            )
        elif intent == "sequential":
            recommended = "read"
            fallback = "query"
            confidence = 0.88
            reason = (
                f"目标文档集仅 {total_docs} 份（共 {total_size_mb:.1f}MB），低于小文档阈值。"
                "顺序阅读需求下 read 覆盖完整内容，优于向量召回。"
            )
        elif intent == "exact":
            recommended = "grep"
            fallback = "query"
            confidence = 0.85
            reason = (
                f"目标文档集仅 {total_docs} 份（共 {total_size_mb:.1f}MB），文档集较小。"
                "精确词汇查找下 grep 可直接定位所有出现位置，优于向量召回。"
            )
        else:  # semantic
            recommended = "query"
            fallback = "read"
            confidence = 0.70
            reason = (
                f"目标文档集仅 {total_docs} 份（共 {total_size_mb:.1f}MB），语义查询可使用"
                " query 或直接 read，选择 query 以获得相关性排序。"
            )
    else:
        recommended = "query"
        confidence = 0.95
        reason = (
            f"全库共 {total_docs} 份文档（总计 {total_size_mb:.1f}MB），远超小文档阈值。"
            " 语义 RAG 混合召回可快速缩小范围，直接阅读代价过高。"
        )
        fallback = None

    # T053: Low-confidence escalation — query recommended but intent is sequential
    low_confidence_note: str | None = None
    if recommended == "query" and intent == "sequential":
        fallback = "read"
        low_confidence_note = (
            "顺序阅读场景 query 可能不完整，建议按需补充 read 以覆盖完整章节内容。"
        )
        if confidence > _LOW_CONFIDENCE_THRESHOLD:
            confidence = max(confidence - 0.15, _LOW_CONFIDENCE_THRESHOLD)

    from src.models.schemas import DocStats, ThresholdInfo

    response = RoutingResponse(
        recommended_skill=recommended,
        fallback_skill=fallback,
        confidence=confidence,
        reason=reason,
        doc_stats=DocStats(
            total_docs=total_docs,
            total_chunks=total_chunks,
            total_size_bytes=total_size_bytes,
            indexed_docs=indexed_docs,
            unindexed_docs=unindexed_docs,
        ),
        thresholds_applied=ThresholdInfo(
            small_doc_threshold=small_threshold,
            small_size_threshold_mb=small_size_mb,
            low_confidence_score_threshold=_LOW_CONFIDENCE_THRESHOLD,
        ),
        low_confidence_note=low_confidence_note,
    )

    # Cache for 60 seconds
    await cache.set(routing_key, json.dumps(response.model_dump()), ttl=60)
    return response
