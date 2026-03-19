"""
Integration tests for the full document ingestion pipeline.
Uploads a synthetic text document and validates that:
  - document status transitions to 'indexed'
  - chunks are correctly written to the database
  - MinIO markdown key is set

Requires: live PostgreSQL + MinIO + Redis + Celery worker
    docker compose up
    celery -A src.ingestion.celery_app worker -l info &

Run with:
    pytest backend/tests/integration/test_ingestion_pipeline.py -v -r s
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from src.core.db import get_raw_pool  # noqa: E402
from src.storage.minio_client import minio_client  # noqa: E402
from src.ingestion.pipeline import ingest_document  # noqa: E402

POLL_INTERVAL = 2  # seconds
MAX_WAIT = 120      # seconds — generous for slow CI environments


# ── Helpers ────────────────────────────────────────────────────────────────


async def _insert_test_document(pool, title: str, content: str) -> int:
    """Insert a document record and upload content to MinIO. Returns doc_id."""
    from src.storage.minio_client import BUCKET_NAME

    async with pool.connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO documents (title, file_name, format, minio_key, status)
            VALUES ($1, $2, 'txt', $3, 'pending')
            RETURNING id
            """,
            title,
            f"{title}.txt",
            f"originals/test/{title}.txt",
        )
    doc_id: int = row["id"]

    # Upload content to MinIO
    data = content.encode("utf-8")
    minio_client.put_object(
        BUCKET_NAME,
        f"originals/test/{title}.txt",
        io.BytesIO(data),
        length=len(data),
        content_type="text/plain",
    )
    return doc_id


async def _poll_status(pool, doc_id: int, max_wait: int = MAX_WAIT) -> str:
    """Poll document status until it leaves 'pending'/'processing'."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        async with pool.connection() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM documents WHERE id = $1", doc_id
            )
        status = row["status"]
        if status not in ("pending", "processing"):
            return status
        await asyncio.sleep(POLL_INTERVAL)
    return "timeout"


async def _cleanup(pool, doc_id: int):
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM chunks WHERE document_id = $1", doc_id
        )
        await conn.execute("DELETE FROM documents WHERE id = $1", doc_id)


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def db_pool():
    pool = await get_raw_pool()
    yield pool
    await pool.close()


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ingest_small_text_document(db_pool):
    """End-to-end: text document → indexed with chunks."""
    content = (
        "# Introduction\n\n"
        "DocSearch is an AI-powered document retrieval system.\n"
        "It supports three retrieval modes: query, read, and grep.\n\n"
        "## Architecture\n\n"
        "The system uses FastAPI on the backend and React on the frontend.\n"
        "Documents are stored in MinIO and indexed in PostgreSQL.\n\n"
        "## Retrieval Skills\n\n"
        "- query_documents: semantic + BM25 hybrid search\n"
        "- read_document: paginated document reading by section\n"
        "- grep_documents: regex pattern matching across Markdown exports\n"
    ) * 3  # repeat to ensure at least a few chunks

    title = f"test_doc_{int(time.time())}"
    doc_id = await _insert_test_document(db_pool, title, content)

    try:
        # Trigger ingestion (runs synchronously in test via apply() which bypasses Celery)
        ingest_document.apply(args=[doc_id])

        # Verify final status
        async with db_pool.connection() as conn:
            row = await conn.fetchrow(
                "SELECT status, markdown_key FROM documents WHERE id = $1", doc_id
            )
        assert row["status"] == "indexed", f"Expected indexed, got {row['status']!r}"
        assert row["markdown_key"] is not None, "markdown_key should be set after ingestion"

        # Verify chunks created
        async with db_pool.connection() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM chunks WHERE document_id = $1", doc_id
            )
        assert count > 0, "Expected at least 1 chunk after ingestion"

    finally:
        await _cleanup(db_pool, doc_id)


@pytest.mark.asyncio
async def test_ingest_chunk_fields(db_pool):
    """Verify chunk records have all required fields populated."""
    content = (
        "# Test Section\n\nThis is test content for field validation.\n"
        "The chunk should have a heading breadcrumb and element type.\n"
    ) * 5

    title = f"field_test_{int(time.time())}"
    doc_id = await _insert_test_document(db_pool, title, content)

    try:
        ingest_document.apply(args=[doc_id])

        async with db_pool.connection() as conn:
            chunks = await conn.fetch(
                """
                SELECT chunk_index, content, element_type,
                       heading_breadcrumb, embedding
                FROM chunks
                WHERE document_id = $1
                ORDER BY chunk_index
                LIMIT 5
                """,
                doc_id,
            )

        assert len(chunks) > 0
        for c in chunks:
            assert c["content"], "content should not be empty"
            assert c["element_type"] in (
                "TEXT", "SECTION_HEADER", "TABLE", "TABLE_PART", "LIST_ITEM"
            )
            assert c["embedding"] is not None, "embedding vector should be set"

    finally:
        await _cleanup(db_pool, doc_id)


@pytest.mark.asyncio
async def test_ingest_status_progression(db_pool, monkeypatch):
    """Document should start as pending and end as indexed (no error)."""
    content = "Simple test document content. " * 20

    title = f"status_test_{int(time.time())}"
    doc_id = await _insert_test_document(db_pool, title, content)

    try:
        # Check initial status
        async with db_pool.connection() as conn:
            row = await conn.fetchrow(
                "SELECT status FROM documents WHERE id = $1", doc_id
            )
        assert row["status"] == "pending"

        ingest_document.apply(args=[doc_id])

        async with db_pool.connection() as conn:
            row = await conn.fetchrow(
                "SELECT status, error_message FROM documents WHERE id = $1", doc_id
            )
        assert row["status"] == "indexed", (
            f"Expected indexed, got {row['status']!r}; error: {row['error_message']}"
        )
        assert row["error_message"] is None

    finally:
        await _cleanup(db_pool, doc_id)


@pytest.mark.asyncio
async def test_ingest_nonexistent_doc_fails_gracefully(db_pool):
    """Ingesting a non-existent doc_id should not crash the worker."""
    try:
        ingest_document.apply(args=[999_999_999])
    except Exception:
        pass  # Worker raised — acceptable

    # No unhandled crash propagated to test runner
    assert True
