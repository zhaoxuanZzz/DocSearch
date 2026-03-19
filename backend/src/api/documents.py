"""T047-T049: Document management API endpoints.

POST /api/v1/documents/upload         — upload + trigger ingestion
GET  /api/v1/documents/               — list with pagination
GET  /api/v1/documents/stats          — library statistics
GET  /api/v1/documents/{id}/status    — status + progress
PUT  /api/v1/documents/{id}           — update (re-ingest)
DELETE /api/v1/documents/{id}         — cascade delete
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from src.core.db import get_raw_pool as get_pool
from src.models.schemas import DocumentResponse, DocumentStatsResponse, DocumentStatusResponse
from src.storage.cache import CacheClient
from src.storage.minio_client import MinioClient

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)

ALLOWED_FORMATS = {"pdf", "docx", "doc", "txt", "md"}


def _ext(file_name: str) -> str:
    return Path(file_name).suffix.lstrip(".").lower()


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile):
    """Upload a document file and trigger the ingestion pipeline."""
    fmt = _ext(file.filename or "unknown.bin")
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=415,
            detail={"error": "UNSUPPORTED_FORMAT", "message": f"Format '{fmt}' is not supported. Allowed: {ALLOWED_FORMATS}"},
        )

    data = await file.read()
    file_size = len(data)
    title = Path(file.filename or "Untitled").stem

    minio = MinioClient()
    pool = await get_pool()

    # Create DB record first to get the doc ID
    async with pool.connection() as conn:
        rows = await conn.execute(
            """
            INSERT INTO documents (title, file_name, format, file_size, minio_key, markdown_key, chunk_count, status)
            VALUES (%s, %s, %s, %s, %s, %s, 0, 'pending')
            RETURNING id, title, file_name, format, file_size, minio_key, markdown_key,
                      chunk_count, status, error_message,
                      created_at::text, updated_at::text
            """,
            (
                title, file.filename, fmt, file_size,
                f"originals/placeholder/{file.filename}",
                None,
            ),
        )
        row = await rows.fetchone()

    doc_id = row[0]
    minio_key = minio.upload_original(doc_id, file.filename or "upload", data)

    # Update minio_key with real key
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE documents SET minio_key = %s WHERE id = %s",
            (minio_key, doc_id),
        )

    # Trigger Celery ingestion task
    try:
        from src.ingestion.pipeline import ingest_document
        task = ingest_document.delay(doc_id)
        # Cache the job task_id
        cache = CacheClient()
        await cache.set(cache.make_job_key(str(task.id)), f"pending:{doc_id}", ttl=3600)
    except Exception as exc:
        logger.warning("Failed to trigger ingestion for doc %s: %s", doc_id, exc)

    return {
        "id": doc_id,
        "title": title,
        "file_name": file.filename,
        "format": fmt,
        "file_size": file_size,
        "minio_key": minio_key,
        "markdown_key": None,
        "chunk_count": 0,
        "status": "pending",
        "error_message": None,
        "created_at": row[10],
        "updated_at": row[11],
    }


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
):
    """List documents with optional status filter and pagination."""
    pool = await get_pool()
    offset = (page - 1) * page_size

    if status:
        sql = """
            SELECT id, title, file_name, format, file_size, minio_key, markdown_key,
                   chunk_count, status, error_message, created_at::text, updated_at::text
            FROM documents
            WHERE status = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        params = (status, page_size, offset)
    else:
        sql = """
            SELECT id, title, file_name, format, file_size, minio_key, markdown_key,
                   chunk_count, status, error_message, created_at::text, updated_at::text
            FROM documents
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """
        params = (page_size, offset)

    async with pool.connection() as conn:
        rows = await conn.execute(sql, params)
        docs = [
            {
                "id": r[0], "title": r[1], "file_name": r[2], "format": r[3],
                "file_size": r[4], "minio_key": r[5], "markdown_key": r[6],
                "chunk_count": r[7], "status": r[8], "error_message": r[9],
                "created_at": r[10], "updated_at": r[11],
            }
            async for r in rows
        ]
    return docs


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=DocumentStatsResponse)
async def document_stats():
    """Return document library statistics (FR-018)."""
    pool = await get_pool()
    async with pool.connection() as conn:
        rows = await conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              COALESCE(SUM(chunk_count), 0) AS total_chunks,
              COUNT(*) FILTER (WHERE status = 'indexed') AS indexed,
              COUNT(*) FILTER (WHERE status = 'processing') AS processing,
              COUNT(*) FILTER (WHERE status = 'pending') AS pending,
              COUNT(*) FILTER (WHERE status = 'failed') AS failed
            FROM documents
            """
        )
        row = await rows.fetchone()
    return {
        "total_documents": row[0],
        "total_chunks": row[1],
        "indexed_documents": row[2],
        "processing_documents": row[3],
        "pending_documents": row[4],
        "failed_documents": row[5],
    }


# ---------------------------------------------------------------------------
# GET /{id}/status
# ---------------------------------------------------------------------------


@router.get("/{doc_id}/status", response_model=DocumentStatusResponse)
async def document_status(doc_id: int):
    """Return current status and ingestion progress for a document."""
    pool = await get_pool()
    async with pool.connection() as conn:
        rows = await conn.execute(
            "SELECT id, status, chunk_count, error_message FROM documents WHERE id = %s",
            (doc_id,),
        )
        row = await rows.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail={"error": "DOC_NOT_FOUND", "message": f"Document {doc_id} not found"})

    # Try to get progress from Redis
    cache = CacheClient()
    job_data = await cache.get(cache.make_job_key(str(doc_id)))
    progress = None
    if job_data:
        try:
            import json
            d = json.loads(job_data)
            progress = d.get("progress")
        except Exception:
            pass

    return {"id": row[0], "status": row[1], "chunk_count": row[2], "error_message": row[3], "progress": progress}


# ---------------------------------------------------------------------------
# PUT /{id} — re-upload / update
# ---------------------------------------------------------------------------


@router.put("/{doc_id}", response_model=DocumentStatusResponse)
async def update_document(doc_id: int, file: UploadFile):
    """Upload a new version of a document and re-trigger ingestion (T048)."""
    pool = await get_pool()
    async with pool.connection() as conn:
        rows = await conn.execute(
            "SELECT id, file_name, minio_key FROM documents WHERE id = %s",
            (doc_id,),
        )
        row = await rows.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail={"error": "DOC_NOT_FOUND", "message": f"Document {doc_id} not found"})

    data = await file.read()
    fmt = _ext(file.filename or row[1])

    minio = MinioClient()
    # Overwrite original file in MinIO
    minio_key = minio.upload_original(doc_id, file.filename or row[1], data)

    async with pool.connection() as conn:
        # Delete old chunks
        await conn.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
        # Reset document status
        await conn.execute(
            """
            UPDATE documents
            SET status = 'pending', chunk_count = 0, error_message = NULL,
                minio_key = %s, markdown_key = NULL, file_size = %s,
                file_name = %s, format = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (minio_key, len(data), file.filename or row[1], fmt, doc_id),
        )

    # Clear caches
    cache = CacheClient()
    await cache.delete(cache.make_doc_status_key(str(doc_id)))
    await cache.delete(cache.make_doc_meta_key(str(doc_id)))

    # Re-trigger ingestion
    try:
        from src.ingestion.pipeline import ingest_document
        ingest_document.delay(doc_id)
    except Exception as exc:
        logger.warning("Failed to re-trigger ingestion for doc %s: %s", doc_id, exc)

    return {"id": doc_id, "status": "pending", "chunk_count": 0, "error_message": None, "progress": 0}


# ---------------------------------------------------------------------------
# DELETE /{id}
# ---------------------------------------------------------------------------


@router.delete("/{doc_id}")
async def delete_document(doc_id: int):
    """Cascade-delete document, chunks, MinIO files, and Redis cache (T047)."""
    pool = await get_pool()
    async with pool.connection() as conn:
        rows = await conn.execute(
            "SELECT id, file_name, format FROM documents WHERE id = %s",
            (doc_id,),
        )
        row = await rows.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail={"error": "DOC_NOT_FOUND", "message": f"Document {doc_id} not found"})

    # Delete chunks + document from DB (cascade)
    async with pool.connection() as conn:
        await conn.execute("DELETE FROM chunks WHERE document_id = %s", (doc_id,))
        await conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))

    # Delete from MinIO
    minio = MinioClient()
    try:
        minio.delete_document(doc_id, row[1], row[2])
    except Exception as exc:
        logger.warning("MinIO delete partial failure for doc %s: %s", doc_id, exc)

    # Clear Redis caches
    cache = CacheClient()
    for key in [
        cache.make_doc_status_key(str(doc_id)),
        cache.make_doc_meta_key(str(doc_id)),
    ]:
        await cache.delete(key)

    return JSONResponse({"message": f"Document {doc_id} deleted successfully"})
