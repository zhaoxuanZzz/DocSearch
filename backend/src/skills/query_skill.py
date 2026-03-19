"""T025 / T031 / T038: query_documents LangChain tool.

Implements the tri-modal retrieval pipeline:
  query → embed → hybrid(vector+BM25) → rerank → context_expand → cache

Cache key: query:{query_hash}:{doc_ids_hash}:{mode}  TTL=300s
"""

from __future__ import annotations

import hashlib
import json
import logging
import time

from langchain_core.tools import tool

from src.core.config import settings
from src.core.db import get_pool
from src.ingestion.embedder import embed_query
from src.models.schemas import ChunkPosition, ChunkResult, ContextWindow, QueryInput, QueryOutput
from src.retrieval.context_expander import expand_context
from src.retrieval.hybrid import hybrid_search
from src.retrieval.reranker import rerank
from src.storage.cache import CacheClient

logger = logging.getLogger(__name__)


def _query_cache_key(inp: QueryInput) -> str:
    q_hash = hashlib.md5(inp.query.encode()).hexdigest()[:8]
    ids_str = ",".join(sorted(str(d) for d in (inp.doc_ids or [])))
    ids_hash = hashlib.md5(ids_str.encode()).hexdigest()[:8]
    return f"query:{q_hash}:{ids_hash}:{inp.mode}"


@tool(args_schema=QueryInput)
async def query_documents(
    query: str,
    doc_ids: list[int] | None = None,
    top_k: int = 5,
    mode: str = "hybrid",
    expand_context: bool = False,
) -> dict:
    """T025: Semantic + keyword hybrid retrieval over indexed documents.

    Returns top-K most relevant chunks with position metadata.
    Uses RRF fusion and optional cross-encoder reranking.
    """
    inp = QueryInput(
        query=query,
        doc_ids=doc_ids,
        top_k=min(top_k, 20),
        mode=mode,
        expand_context=expand_context,
    )
    t_start = time.monotonic()
    warnings: list[str] = []

    # --- Input validation ---
    if not inp.query.strip():
        raise ValueError("QUERY_EMPTY: query must not be empty")
    if inp.mode not in ("semantic", "keyword", "hybrid"):
        raise ValueError(f"INVALID_MODE: {inp.mode}")
    if top_k > 20:
        inp.top_k = 20
        warnings.append("top_k clamped to 20")

    # --- Cache lookup ---
    cache = CacheClient()
    cache_key = _query_cache_key(inp)
    cached = await cache.get(cache_key)
    if cached:
        return json.loads(cached)

    # --- Encode query ---
    embedding, was_truncated = embed_query(inp.query)
    if was_truncated:
        warnings.append("query truncated to 2048 characters before embedding")

    # --- Retrieve ---
    pool = await get_pool()
    top_n = settings.reranker_top_n  # e.g. 20

    hybrid_candidates = await hybrid_search(
        pool=pool,
        query_embedding=embedding if inp.mode != "keyword" else None,
        query_text=inp.query,
        doc_ids=inp.doc_ids,
        top_k=top_n,
        mode=inp.mode,
    )

    total_found = len(hybrid_candidates)

    # --- Fetch chunk content from DB ---
    if not hybrid_candidates:
        output = QueryOutput(
            results=[],
            total_found=0,
            strategy_used=inp.mode,
            query_truncated=was_truncated,
            warnings=warnings + ["No results found in the document library"],
            latency_ms=round((time.monotonic() - t_start) * 1000, 2),
        )
        return output.model_dump()

    chunk_ids = [c.chunk_id for c in hybrid_candidates]

    async with pool.connection() as conn:
        rows = await conn.execute(
            """
            SELECT c.id, c.document_id, d.title, c.content, c.chunk_index,
                   c.page_no, c.heading_breadcrumb, c.element_type,
                   c.element_index_on_page
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id = ANY(%s)
            """,
            (chunk_ids,),
        )
        chunk_rows = {row[0]: row async for row in rows}

    # --- Build candidate dicts for reranker ---
    candidates_for_rerank = []
    for c in hybrid_candidates:
        row = chunk_rows.get(c.chunk_id)
        if row is None:
            continue
        candidates_for_rerank.append(
            {
                "chunk_id": c.chunk_id,
                "document_id": row[1],
                "document_title": row[2],
                "content": row[3],
                "chunk_index": row[4],
                "page_no": row[5],
                "heading_breadcrumb": row[6],
                "element_type": row[7],
                "element_index_on_page": row[8],
                "rrf_score": c.rrf_score,
            }
        )

    # --- Rerank ---
    reranked, rerank_latency = rerank(inp.query, candidates_for_rerank, top_k=inp.top_k)

    # --- Assemble results ---
    results: list[ChunkResult] = []
    for item in reranked:
        position = ChunkPosition(
            page_no=item["page_no"],
            heading_breadcrumb=item["heading_breadcrumb"] or "",
            element_type=item["element_type"] or "PARAGRAPH",
            element_index_on_page=item["element_index_on_page"],
            chunk_index=item["chunk_index"],
        )

        ctx: ContextWindow | None = None
        if inp.expand_context:
            window = await expand_context(
                pool, item["chunk_id"], item["document_id"], item["chunk_index"]
            )
            # Build minimal ChunkResult for neighbours
            prev_cr = None
            if window.prev_content:
                prev_cr = ChunkResult(
                    chunk_id=0,
                    document_id=item["document_id"],
                    document_title=item["document_title"],
                    content=window.prev_content,
                    score=0.0,
                    position=ChunkPosition(
                        page_no=None, heading_breadcrumb="", element_type="PARAGRAPH",
                        element_index_on_page=None, chunk_index=item["chunk_index"] - 1,
                    ),
                )
            next_cr = None
            if window.next_content:
                next_cr = ChunkResult(
                    chunk_id=0,
                    document_id=item["document_id"],
                    document_title=item["document_title"],
                    content=window.next_content,
                    score=0.0,
                    position=ChunkPosition(
                        page_no=None, heading_breadcrumb="", element_type="PARAGRAPH",
                        element_index_on_page=None, chunk_index=item["chunk_index"] + 1,
                    ),
                )
            ctx = ContextWindow(prev_chunk=prev_cr, next_chunk=next_cr)

        results.append(
            ChunkResult(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                document_title=item["document_title"],
                content=item["content"],
                score=round(item["rerank_score"], 4),
                position=position,
                context=ctx,
            )
        )

    latency_ms = round((time.monotonic() - t_start) * 1000, 2)
    output = QueryOutput(
        results=results,
        total_found=total_found,
        strategy_used=inp.mode,
        query_truncated=was_truncated,
        warnings=warnings,
        latency_ms=latency_ms,
    )
    output_dict = output.model_dump()

    # Cache result
    await cache.set(cache_key, json.dumps(output_dict, default=str), ttl=300)

    return output_dict
