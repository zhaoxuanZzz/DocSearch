"""T062: Prometheus metrics endpoint.

Exposes:
  - query_latency_seconds histogram (p50/p95/p99)
  - ingestion_queue_depth gauge
  - cache_hit / cache_miss counters
  - document_count gauge (by status)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["metrics"])
logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        multiprocess,
    )
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    logger.warning("prometheus_client not installed; /metrics returns empty response")

if _PROM_AVAILABLE:
    _registry = CollectorRegistry()

    query_latency = Histogram(
        "docsearch_query_latency_seconds",
        "Query skill end-to-end latency in seconds",
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
        registry=_registry,
    )
    cache_hits = Counter("docsearch_cache_hits_total", "Redis cache hits", registry=_registry)
    cache_misses = Counter("docsearch_cache_misses_total", "Redis cache misses", registry=_registry)
    ingestion_queue = Gauge("docsearch_ingestion_queue_depth", "Celery ingestion queue depth", registry=_registry)
    docs_by_status = Gauge(
        "docsearch_documents_total",
        "Document count by status",
        ["status"],
        registry=_registry,
    )


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint():
    """GET /api/v1/metrics — Prometheus scrape endpoint (T062)."""
    if not _PROM_AVAILABLE:
        return PlainTextResponse("# prometheus_client not installed\n", status_code=200)

    # Refresh document gauge from DB
    try:
        from src.core.db import get_pool
        pool = await get_pool()
        async with pool.connection() as conn:
            rows = await conn.execute(
                """
                SELECT status, COUNT(*) FROM documents GROUP BY status
                """
            )
            async for row in rows:
                docs_by_status.labels(status=row[0]).set(row[1])
    except Exception as exc:
        logger.warning("Metrics DB query failed: %s", exc)

    # Refresh Celery queue depth
    try:
        from src.ingestion.celery_app import celery_app
        inspect = celery_app.control.inspect()
        active = inspect.active() or {}
        depth = sum(len(v) for v in active.values())
        ingestion_queue.set(depth)
    except Exception:
        pass

    return PlainTextResponse(
        generate_latest(_registry).decode(),
        media_type=CONTENT_TYPE_LATEST,
    )
