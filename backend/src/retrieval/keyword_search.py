"""T021: ParadeDB pg_search BM25 keyword retrieval."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool


@dataclass
class BM25Candidate:
    chunk_id: int
    document_id: int
    bm25_rank: float  # BM25 relevance rank score
    rank: int         # ordinal rank (1 = best)


async def bm25_search(
    pool: AsyncConnectionPool,
    query_text: str,
    doc_ids: list[int] | None = None,
    top_n: int = 20,
) -> list[BM25Candidate]:
    """
    T021: BM25 keyword search via ParadeDB pg_search.

    Uses `content @@@` operator for BM25 ranking. Filters by doc_ids when provided.
    """
    if doc_ids:
        sql = """
            SELECT id, document_id,
                   paradedb.score(id) AS bm25_rank
            FROM chunks
            WHERE (content @@@ %s OR heading_breadcrumb @@@ %s)
              AND document_id = ANY(%s)
            ORDER BY bm25_rank DESC
            LIMIT %s
        """
        params = [query_text, query_text, doc_ids, top_n]
    else:
        sql = """
            SELECT id, document_id,
                   paradedb.score(id) AS bm25_rank
            FROM chunks
            WHERE content @@@ %s OR heading_breadcrumb @@@ %s
            ORDER BY bm25_rank DESC
            LIMIT %s
        """
        params = [query_text, query_text, top_n]

    async with pool.connection() as conn:
        rows = await conn.execute(sql, params)
        results = await rows.fetchall()

    return [
        BM25Candidate(
            chunk_id=row[0],
            document_id=row[1],
            bm25_rank=float(row[2]) if row[2] is not None else 0.0,
            rank=i + 1,
        )
        for i, row in enumerate(results)
    ]
