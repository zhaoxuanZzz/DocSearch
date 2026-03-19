"""T022: RRF (Reciprocal Rank Fusion) hybrid retrieval combining vector + BM25.

T036: Mode dispatch logic (semantic / keyword / hybrid).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from psycopg_pool import AsyncConnectionPool

from src.core.config import settings
from src.retrieval.keyword_search import BM25Candidate, bm25_search
from src.retrieval.vector_search import VectorCandidate, vector_search


@dataclass
class HybridCandidate:
    chunk_id: int
    document_id: int
    rrf_score: float
    vector_rank: int | None = None
    bm25_rank: int | None = None


async def hybrid_search(
    pool: AsyncConnectionPool,
    query_embedding: list[float] | None,
    query_text: str,
    doc_ids: list[int] | None = None,
    top_k: int = 20,
    mode: str = "hybrid",
) -> list[HybridCandidate]:
    """
    T022 / T036: Dispatch retrieval by mode and fuse results with RRF.

    mode="semantic"  → vector only
    mode="keyword"   → BM25 only
    mode="hybrid"    → RRF fusion of both
    """
    k = settings.rrf_k  # typically 60

    if mode == "semantic":
        if query_embedding is None:
            raise ValueError("query_embedding required for semantic mode")
        vector_candidates = await vector_search(pool, query_embedding, doc_ids, top_n=top_k)
        return [
            HybridCandidate(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                rrf_score=1.0 / (k + c.rank),
                vector_rank=c.rank,
            )
            for c in vector_candidates
        ]

    if mode == "keyword":
        bm25_candidates = await bm25_search(pool, query_text, doc_ids, top_n=top_k)
        return [
            HybridCandidate(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                rrf_score=1.0 / (k + c.rank),
                bm25_rank=c.rank,
            )
            for c in bm25_candidates
        ]

    # hybrid: RRF fusion
    if query_embedding is None:
        raise ValueError("query_embedding required for hybrid mode")

    vector_results: list[VectorCandidate] = await vector_search(
        pool, query_embedding, doc_ids, top_n=20
    )
    bm25_results: list[BM25Candidate] = await bm25_search(
        pool, query_text, doc_ids, top_n=20
    )

    # Build score maps
    vector_map: dict[int, VectorCandidate] = {c.chunk_id: c for c in vector_results}
    bm25_map: dict[int, BM25Candidate] = {c.chunk_id: c for c in bm25_results}

    all_chunk_ids = set(vector_map) | set(bm25_map)
    fused: list[HybridCandidate] = []
    for chunk_id in all_chunk_ids:
        v = vector_map.get(chunk_id)
        b = bm25_map.get(chunk_id)
        score = 0.0
        if v:
            score += 1.0 / (k + v.rank)
        if b:
            score += 1.0 / (k + b.rank)
        fused.append(
            HybridCandidate(
                chunk_id=chunk_id,
                document_id=(v or b).document_id,
                rrf_score=score,
                vector_rank=v.rank if v else None,
                bm25_rank=b.rank if b else None,
            )
        )

    fused.sort(key=lambda c: c.rrf_score, reverse=True)
    return fused[:top_k]
