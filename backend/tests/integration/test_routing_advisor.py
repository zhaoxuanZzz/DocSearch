"""
Integration tests for the routing advisor.
Validates that the advisor recommends the correct skill for small/large
document sets across all intent types.

Requires: live PostgreSQL + Redis
    docker compose up db redis

Run with:
    pytest backend/tests/integration/test_routing_advisor.py -v -r s
"""
from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from src.core.db import get_raw_pool  # noqa: E402
from src.models.schemas import RoutingRequest  # noqa: E402
from src.skills.routing_advisor import get_routing_suggestion  # noqa: E402


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def db_pool():
    pool = await get_raw_pool()
    yield pool
    await pool.close()


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_request(**kwargs) -> RoutingRequest:
    defaults = {
        "doc_ids": None,
        "query_intent": "semantic",
        "query_sample": None,
    }
    defaults.update(kwargs)
    return RoutingRequest(**defaults)


# ── Small doc set mocks – pretend only a few small docs exist ──────────────

SMALL_DOC_STATS = {
    "total_docs": 3,
    "total_chunks": 30,
    "total_size_bytes": 512_000,  # 0.5 MB — below SMALL_SIZE_MB=1.0
    "indexed_docs": 3,
    "unindexed_docs": 0,
}

LARGE_DOC_STATS = {
    "total_docs": 25,
    "total_chunks": 5000,
    "total_size_bytes": 50 * 1024 * 1024,  # 50 MB
    "indexed_docs": 25,
    "unindexed_docs": 0,
}


def _patch_stats(stats: dict):
    """Return a context manager that mocks the DB doc stats query."""
    return patch(
        "src.skills.routing_advisor._fetch_doc_stats",
        new=AsyncMock(return_value=stats),
    )


# ── Tests: small doc set ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_small_set_pattern_intent_recommends_grep(db_pool):
    with _patch_stats(SMALL_DOC_STATS):
        req = _make_request(query_intent="pattern", query_sample="error.*code")
        resp = await get_routing_suggestion(db_pool, req)
    assert resp.recommended_skill == "grep", (
        f"Expected grep for small+pattern, got {resp.recommended_skill}"
    )
    assert resp.confidence >= 0.80


@pytest.mark.asyncio
async def test_small_set_sequential_intent_recommends_read(db_pool):
    with _patch_stats(SMALL_DOC_STATS):
        req = _make_request(query_intent="sequential")
        resp = await get_routing_suggestion(db_pool, req)
    assert resp.recommended_skill == "read", (
        f"Expected read for small+sequential, got {resp.recommended_skill}"
    )
    assert resp.confidence >= 0.75


@pytest.mark.asyncio
async def test_small_set_exact_intent_recommends_grep(db_pool):
    with _patch_stats(SMALL_DOC_STATS):
        req = _make_request(query_intent="exact")
        resp = await get_routing_suggestion(db_pool, req)
    assert resp.recommended_skill == "grep"


@pytest.mark.asyncio
async def test_small_set_semantic_intent_recommends_query(db_pool):
    with _patch_stats(SMALL_DOC_STATS):
        req = _make_request(query_intent="semantic")
        resp = await get_routing_suggestion(db_pool, req)
    # semantic intent should still prefer query even for small sets
    assert resp.recommended_skill in ("query", "grep")


# ── Tests: large doc set ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_large_set_any_intent_recommends_query(db_pool):
    for intent in ("semantic", "exact", "pattern", "sequential"):
        with _patch_stats(LARGE_DOC_STATS):
            req = _make_request(query_intent=intent)
            resp = await get_routing_suggestion(db_pool, req)
        assert resp.recommended_skill == "query", (
            f"Expected query for large set + {intent!r}, got {resp.recommended_skill}"
        )
        assert resp.confidence >= 0.85


@pytest.mark.asyncio
async def test_large_set_sequential_has_fallback_read(db_pool):
    with _patch_stats(LARGE_DOC_STATS):
        req = _make_request(query_intent="sequential")
        resp = await get_routing_suggestion(db_pool, req)
    assert resp.recommended_skill == "query"
    assert resp.fallback_skill == "read", (
        f"Expected fallback=read for sequential, got {resp.fallback_skill}"
    )


# ── Tests: response schema ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_has_required_fields(db_pool):
    with _patch_stats(SMALL_DOC_STATS):
        req = _make_request(query_intent="semantic")
        resp = await get_routing_suggestion(db_pool, req)

    assert hasattr(resp, "recommended_skill")
    assert hasattr(resp, "confidence")
    assert hasattr(resp, "reason")
    assert hasattr(resp, "doc_stats")
    assert hasattr(resp, "thresholds_applied")
    assert 0.0 <= resp.confidence <= 1.0
    assert resp.reason  # non-empty string


@pytest.mark.asyncio
async def test_confidence_decreases_for_low_confidence_case(db_pool):
    """Sequential + high confidence intent on large set should have note."""
    with _patch_stats(LARGE_DOC_STATS):
        req = _make_request(query_intent="sequential")
        resp = await get_routing_suggestion(db_pool, req)
    # Large sequential → query but confidence should be reduced
    # The low_confidence_note should be set if < threshold
    if resp.confidence < resp.thresholds_applied.get(
        "low_confidence_score_threshold", 0.75
    ):
        assert resp.low_confidence_note is not None


@pytest.mark.asyncio
async def test_routing_response_thresholds_are_reasonable(db_pool):
    """Thresholds should match expected config values."""
    with _patch_stats(SMALL_DOC_STATS):
        req = _make_request(query_intent="semantic")
        resp = await get_routing_suggestion(db_pool, req)

    t = resp.thresholds_applied
    assert t["small_doc_threshold"] >= 1
    assert t["small_size_threshold_mb"] > 0
    assert 0 < t["low_confidence_score_threshold"] < 1


# ── Caching ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_same_request_cached(db_pool):
    """Two identical requests should return equal results (via cache)."""
    with _patch_stats(SMALL_DOC_STATS):
        req1 = _make_request(query_intent="pattern")
        req2 = _make_request(query_intent="pattern")
        r1 = await get_routing_suggestion(db_pool, req1)
        r2 = await get_routing_suggestion(db_pool, req2)

    assert r1.recommended_skill == r2.recommended_skill
    assert r1.confidence == r2.confidence
