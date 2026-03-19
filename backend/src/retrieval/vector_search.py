"""T020: pgvector HNSW semantic vector search."""

from __future__ import annotations

from dataclasses import dataclass

from pgvector.psycopg import Vector
from psycopg_pool import AsyncConnectionPool

from src.core.config import settings


@dataclass
class VectorCandidate:
    chunk_id: int
    document_id: int
    score: float  # cosine similarity (0-1)
    rank: int


async def vector_search(
    pool: AsyncConnectionPool,
    query_embedding: list[float],
    doc_ids: list[int] | None = None,
    top_n: int = 20,
) -> list[VectorCandidate]:
    """
    T020: HNSW cosine similarity search via pgvector.

    Returns top_n candidates sorted by cosine similarity (descending).
    Filters by doc_ids when provided.
    """
    await _set_ef_search(pool)
    vec = Vector(query_embedding)

    if doc_ids:
        sql = """
            SELECT id, document_id,
                   1 - (embedding <=> %s) AS score
            FROM chunks
            WHERE document_id = ANY(%s)
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s
        """
        params = [vec, doc_ids, vec, top_n]
    else:
        sql = """
            SELECT id, document_id,
                   1 - (embedding <=> %s) AS score
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s
            LIMIT %s
        """
        params = [vec, vec, top_n]

    async with pool.connection() as conn:
        rows = await conn.execute(sql, params)
        results = await rows.fetchall()

    return [
        VectorCandidate(
            chunk_id=row[0],
            document_id=row[1],
            score=float(row[2]),
            rank=i + 1,
        )
        for i, row in enumerate(results)
    ]


async def _set_ef_search(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        await conn.execute(f"SET hnsw.ef_search = {settings.hnsw_ef_search}")
        await conn.rollback()
