"""T028 / T032 / T033: FastAPI skill endpoints.

Endpoints:
  POST /api/v1/skills/query
  POST /api/v1/skills/read
  POST /api/v1/skills/grep
  POST /api/v1/skills/query/batch  (T033)
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request

from src.models.schemas import GrepInput, QueryInput, QueryOutput, ReadInput
from src.skills.grep_skill import grep_documents
from src.skills.query_skill import query_documents
from src.skills.read_skill import read_document

router = APIRouter(tags=["skills"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: map ValueError codes to HTTP status codes
# ---------------------------------------------------------------------------

_ERROR_STATUS: dict[str, int] = {
    "QUERY_EMPTY": 400,
    "INVALID_MODE": 400,
    "NO_DOCS_FOUND": 404,
    "INDEX_NOT_READY": 503,
    "INVALID_CURSOR": 400,
    "DOC_NOT_FOUND": 404,
    "POSITION_NOT_FOUND": 404,
    "DOC_NOT_INDEXED": 503,
    "PATTERN_EMPTY": 400,
    "INVALID_PATTERN": 400,
    "DOC_LIMIT_EXCEEDED": 400,
    "DOCS_NOT_INDEXED": 503,
}


def _map_error(exc: ValueError) -> HTTPException:
    msg = str(exc)
    for code, status in _ERROR_STATUS.items():
        if msg.startswith(code):
            return HTTPException(status_code=status, detail={"error": code, "message": msg})
    return HTTPException(status_code=500, detail={"error": "INTERNAL_ERROR", "message": msg})


# ---------------------------------------------------------------------------
# query endpoint
# ---------------------------------------------------------------------------


@router.post("/query")
async def query_endpoint(body: QueryInput):
    """POST /api/v1/skills/query — T028 / T032"""
    # Input guard – T032
    if not body.query or not body.query.strip():
        raise HTTPException(status_code=400, detail={"error": "QUERY_EMPTY", "message": "query must not be empty"})
    if body.mode not in ("semantic", "keyword", "hybrid"):
        raise HTTPException(status_code=400, detail={"error": "INVALID_MODE", "message": f"mode '{body.mode}' is not valid"})

    # Clamp top_k
    warnings: list[str] = []
    if body.top_k and body.top_k > 20:
        body.top_k = 20
        warnings.append("top_k clamped to 20")

    try:
        result = await query_documents.ainvoke(body.model_dump())
    except ValueError as exc:
        raise _map_error(exc)

    if warnings and isinstance(result, dict):
        result.setdefault("warnings", []).extend(warnings)

    return result


# ---------------------------------------------------------------------------
# read endpoint
# ---------------------------------------------------------------------------


@router.post("/read")
async def read_endpoint(body: ReadInput):
    """POST /api/v1/skills/read — T028"""
    try:
        result = await read_document.ainvoke(body.model_dump())
    except ValueError as exc:
        raise _map_error(exc)
    return result


# ---------------------------------------------------------------------------
# grep endpoint
# ---------------------------------------------------------------------------


@router.post("/grep")
async def grep_endpoint(body: GrepInput):
    """POST /api/v1/skills/grep — T028"""
    if not body.pattern or not body.pattern.strip():
        raise HTTPException(status_code=400, detail={"error": "PATTERN_EMPTY", "message": "pattern must not be empty"})
    try:
        result = await grep_documents.ainvoke(body.model_dump())
    except ValueError as exc:
        raise _map_error(exc)
    return result


# ---------------------------------------------------------------------------
# batch query endpoint (T033 / FR-015)
# ---------------------------------------------------------------------------


from pydantic import BaseModel


class BatchQueryRequest(BaseModel):
    queries: list[QueryInput]


@router.post("/query/batch")
async def batch_query_endpoint(body: BatchQueryRequest):
    """POST /api/v1/skills/query/batch — T033 / FR-015

    Concurrently executes multiple queries and returns their results in order.
    """
    if not body.queries:
        raise HTTPException(status_code=400, detail={"error": "QUERY_EMPTY", "message": "queries list is empty"})

    async def _run(q: QueryInput) -> dict:
        try:
            return await query_documents.ainvoke(q.model_dump())
        except ValueError as exc:
            http_exc = _map_error(exc)
            return {"error": http_exc.detail}

    results: list[dict] = await asyncio.gather(*[_run(q) for q in body.queries])
    return {"results": results}
