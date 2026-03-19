"""T024: Context window expander.

Fetches adjacent chunks (prev / next) to widen the read window when
expand_context=True on QueryInput.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import AsyncConnectionPool


@dataclass
class ContextWindow:
    chunk_id: int
    document_id: int
    chunk_index: int
    content: str
    prev_content: str | None = None
    next_content: str | None = None


async def expand_context(
    pool: AsyncConnectionPool,
    chunk_id: int,
    document_id: int,
    chunk_index: int,
) -> ContextWindow:
    """Fetch the target chunk plus its immediate neighbours."""
    async with pool.connection() as conn:
        # Fetch current, prev, next in one round-trip
        rows = await conn.execute(
            """
            SELECT id, chunk_index, content
            FROM chunks
            WHERE document_id = %s
              AND chunk_index BETWEEN %s AND %s
            ORDER BY chunk_index
            """,
            (document_id, chunk_index - 1, chunk_index + 1),
        )
        results = {row[1]: row[2] async for row in rows}

    return ContextWindow(
        chunk_id=chunk_id,
        document_id=document_id,
        chunk_index=chunk_index,
        content=results.get(chunk_index, ""),
        prev_content=results.get(chunk_index - 1),
        next_content=results.get(chunk_index + 1),
    )
