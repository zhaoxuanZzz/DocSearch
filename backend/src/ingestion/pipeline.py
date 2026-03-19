"""T046: Full ingestion Celery pipeline task.

ingest_document(document_id) executes the following stages:
  1. Download original file from MinIO
  2. Docling conversion → Markdown + element metadata
  3. Upload Markdown to MinIO
  4. Chunk document (table-aware)
  5. Batch embed chunks (BAAI/bge-m3)
  6. Bulk insert chunks into PostgreSQL
  7. Update documents.status → 'indexed'

Progress tracked in Redis as JSON: {stage, progress(0-100), message}
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path

from celery import states

from src.ingestion.celery_app import celery_app
from src.core.config import settings
from pgvector.psycopg import Vector

logger = logging.getLogger(__name__)


def _set_progress(task, stage: str, progress: int, message: str = ""):
    """Update Redis job progress via Celery update_state."""
    task.update_state(
        state="PROGRESS",
        meta={"stage": stage, "progress": progress, "message": message},
    )


@celery_app.task(bind=True, name="src.ingestion.pipeline.ingest_document")
def ingest_document(self, document_id: int) -> dict:
    """Celery task: full ingestion pipeline for one document."""
    return asyncio.get_event_loop().run_until_complete(
        _async_ingest(self, document_id)
    )


async def _async_ingest(task, document_id: int) -> dict:
    from psycopg_pool import AsyncConnectionPool

    from src.core.config import settings
    from src.core.db import get_pool
    from src.ingestion.chunker import chunk_document
    from src.ingestion.converter import convert_document
    from src.ingestion.embedder import embed_texts
    from src.storage.cache import CacheClient
    from src.storage.minio_client import MinioClient

    pool = await get_pool()
    minio = MinioClient()
    cache = CacheClient()

    async def _fail(msg: str):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE documents SET status='failed', error_message=%s, updated_at=NOW() WHERE id=%s",
                (msg, document_id),
            )
        return {"status": "failed", "error": msg}

    # --- Stage 1: Mark processing ---
    try:
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE documents SET status='processing', updated_at=NOW() WHERE id=%s",
                (document_id,),
            )
    except Exception as exc:
        return await _fail(f"DB update failed: {exc}")

    _set_progress(task, "download", 5, "Downloading from MinIO")

    # --- Stage 2: Download original ---
    try:
        async with pool.connection() as conn:
            rows = await conn.execute(
                "SELECT file_name, format, minio_key FROM documents WHERE id=%s",
                (document_id,),
            )
            doc_row = await rows.fetchone()
        if doc_row is None:
            return await _fail("Document not found")
        file_name, fmt, minio_key = doc_row

        raw_bytes = minio.download_original(document_id, file_name)
    except Exception as exc:
        return await _fail(f"Download failed: {exc}")

    _set_progress(task, "convert", 15, "Converting document")

    # --- Stage 3: Docling conversion ---
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        conversion = convert_document(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
    except Exception as exc:
        return await _fail(f"Conversion failed: {exc}")

    _set_progress(task, "upload_md", 30, "Uploading Markdown")

    # --- Stage 4: Upload Markdown ---
    try:
        minio.upload_markdown(document_id, conversion.markdown)
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE documents SET markdown_key=%s, updated_at=NOW() WHERE id=%s",
                (f"markdown/{document_id}/converted.md", document_id),
            )
    except Exception as exc:
        return await _fail(f"Markdown upload failed: {exc}")

    _set_progress(task, "chunk", 40, "Chunking document")

    # --- Stage 5: Chunk ---
    try:
        chunks = chunk_document(conversion)
    except Exception as exc:
        return await _fail(f"Chunking failed: {exc}")

    if not chunks:
        return await _fail("No chunks produced – document may be empty")

    _set_progress(task, "embed", 55, f"Embedding {len(chunks)} chunks")

    # --- Stage 6: Batch embed ---
    try:
        texts = [c.content for c in chunks]
        batch_size = 32
        all_embeddings: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            all_embeddings.extend(embed_texts(batch))
            prog = 55 + int(35 * (start + len(batch)) / len(texts))
            _set_progress(task, "embed", prog, f"Embedded {start + len(batch)}/{len(texts)}")
    except Exception as exc:
        return await _fail(f"Embedding failed: {exc}")

    _set_progress(task, "index", 90, "Writing to database")

    # --- Stage 7: Bulk insert chunks ---
    try:
        async with pool.connection() as conn:
            # Delete old chunks (re-ingest case)
            await conn.execute("DELETE FROM chunks WHERE document_id=%s", (document_id,))

            for chunk, embedding in zip(chunks, all_embeddings):
                await conn.execute(
                    """
                    INSERT INTO chunks (
                        document_id, chunk_index, content, embedding,
                        page_no, bbox, heading_breadcrumb, element_type,
                        element_index_on_page, markdown_line_start, markdown_line_end,
                        chunk_type, has_table_header
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        document_id, chunk.chunk_index, chunk.content, Vector(embedding),
                        chunk.page_no, json.dumps(chunk.bbox) if chunk.bbox else None,
                        chunk.heading_breadcrumb, chunk.element_type,
                        chunk.element_index_on_page, chunk.markdown_line_start,
                        chunk.markdown_line_end, chunk.chunk_type, chunk.has_table_header,
                    ),
                )

            # Update document record
            await conn.execute(
                """
                UPDATE documents
                SET status='indexed', chunk_count=%s, error_message=NULL, updated_at=NOW()
                WHERE id=%s
                """,
                (len(chunks), document_id),
            )
    except Exception as exc:
        return await _fail(f"DB insert failed: {exc}")

    # --- Clear related caches ---
    await cache.delete(cache.make_doc_status_key(str(document_id)))
    await cache.delete(cache.make_doc_meta_key(str(document_id)))

    _set_progress(task, "done", 100, f"Indexed {len(chunks)} chunks successfully")
    logger.info("Document %s indexed: %d chunks", document_id, len(chunks))
    return {"status": "indexed", "chunk_count": len(chunks)}
