"""T026 / T039-T043: read_document LangChain tool.

Implements paginated sequential reading of a single document.

Supports two modes:
- token : accumulate chunks until max_tokens
- heading: return all chunks under the same top-level heading

Cursor = base64(json({"chunk_index": N}))
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

from src.core.db import get_pool
from src.models.schemas import ChunkPosition, ReadInput, ReadOutput
from src.skills.cursor import decode_cursor, encode_cursor

logger = logging.getLogger(__name__)

_APPROX_CHARS_PER_TOKEN = 4


def _count_tokens(text: str) -> int:
    return max(1, len(text) // _APPROX_CHARS_PER_TOKEN)


@tool(args_schema=ReadInput)
async def read_document(
    doc_id: int,
    start_page: int | None = None,
    start_breadcrumb: str | None = None,
    cursor: str | None = None,
    mode: str = "heading",
    max_tokens: int = 2000,
) -> dict:
    """T026: Read a document sequentially by token count or heading block.

    Returns the current page content and a cursor for the next page.
    """
    max_tokens = min(max_tokens, 4000)
    pool = await get_pool()

    async with pool.connection() as conn:
        # Verify document exists and is indexed
        doc_rows = await conn.execute(
            "SELECT id, title, status FROM documents WHERE id = %s",
            (doc_id,),
        )
        doc_row = await doc_rows.fetchone()

    if doc_row is None:
        raise ValueError(f"DOC_NOT_FOUND: document {doc_id} does not exist")
    if doc_row[2] != "indexed":
        raise ValueError(f"DOC_NOT_INDEXED: document {doc_id} is not yet indexed")

    doc_title = doc_row[1]

    # --- Determine starting chunk_index ---
    start_index: int = 0

    if cursor:
        # cursor takes priority over start_page / start_breadcrumb
        start_index = decode_cursor(cursor)
    elif start_breadcrumb:
        # T039: SQL prefix match — find the lowest chunk_index matching breadcrumb
        async with pool.connection() as conn:
            rows = await conn.execute(
                """
                SELECT MIN(chunk_index)
                FROM chunks
                WHERE document_id = %s
                  AND heading_breadcrumb LIKE %s
                """,
                (doc_id, f"{start_breadcrumb}%"),
            )
            row = await rows.fetchone()
        if row is None or row[0] is None:
            raise ValueError(
                f"POSITION_NOT_FOUND: no chunk matches breadcrumb '{start_breadcrumb}'"
            )
        start_index = row[0]
    elif start_page is not None:
        async with pool.connection() as conn:
            rows = await conn.execute(
                """
                SELECT MIN(chunk_index)
                FROM chunks
                WHERE document_id = %s AND page_no >= %s
                """,
                (doc_id, start_page),
            )
            row = await rows.fetchone()
        if row is None or row[0] is None:
            raise ValueError(
                f"POSITION_NOT_FOUND: no chunk found at or after page {start_page}"
            )
        start_index = row[0]

    # --- Fetch chunks based on mode ---
    async with pool.connection() as conn:
        if mode == "token":
            # T040: token mode — read chunks sequentially until max_tokens
            rows = await conn.execute(
                """
                SELECT id, chunk_index, content, page_no, heading_breadcrumb,
                       element_type, element_index_on_page
                FROM chunks
                WHERE document_id = %s AND chunk_index >= %s
                ORDER BY chunk_index
                LIMIT 500
                """,
                (doc_id, start_index),
            )
            chunks = [row async for row in rows]
        else:
            # T040: heading mode — find the top-level heading at start_index
            # then read all chunks under the same heading subtree
            # First fetch the breadcrumb of the start chunk
            rows = await conn.execute(
                """
                SELECT heading_breadcrumb
                FROM chunks
                WHERE document_id = %s AND chunk_index = %s
                """,
                (doc_id, start_index),
            )
            anchor_row = await rows.fetchone()
            if anchor_row is None:
                raise ValueError(
                    f"POSITION_NOT_FOUND: chunk_index {start_index} not found"
                )
            anchor_breadcrumb = anchor_row[0] or ""
            # Extract the top-level breadcrumb segment (first "> "-separated part)
            top_level = anchor_breadcrumb.split(" > ")[0] if anchor_breadcrumb else ""

            rows = await conn.execute(
                """
                SELECT id, chunk_index, content, page_no, heading_breadcrumb,
                       element_type, element_index_on_page
                FROM chunks
                WHERE document_id = %s
                  AND chunk_index >= %s
                  AND (heading_breadcrumb LIKE %s OR heading_breadcrumb = %s)
                ORDER BY chunk_index
                """,
                (doc_id, start_index, f"{top_level}%", top_level),
            )
            chunks = [row async for row in rows]

    if not chunks:
        return ReadOutput(
            doc_id=doc_id,
            doc_title=doc_title,
            content="",
            chunks_returned=0,
            position_start=ChunkPosition(
                page_no=None,
                heading_breadcrumb="",
                element_type="PARAGRAPH",
                element_index_on_page=None,
                chunk_index=start_index,
            ),
            position_end=ChunkPosition(
                page_no=None,
                heading_breadcrumb="",
                element_type="PARAGRAPH",
                element_index_on_page=None,
                chunk_index=start_index,
            ),
            next_cursor=None,
            is_end_of_document=True,
            mode_used=mode,
        ).model_dump()

    # --- Select which chunks to include this page ---
    selected_chunks = []
    token_count = 0

    if mode == "token":
        for chunk in chunks:
            t = _count_tokens(chunk[2])
            if token_count + t > max_tokens and selected_chunks:
                break
            selected_chunks.append(chunk)
            token_count += t
    else:
        # heading mode: return all fetched chunks (already filtered to heading block)
        selected_chunks = chunks

    # --- Check max_index in document for is_end_of_document ---
    last_selected_index = selected_chunks[-1][1]
    async with pool.connection() as conn:
        rows = await conn.execute(
            "SELECT MAX(chunk_index) FROM chunks WHERE document_id = %s",
            (doc_id,),
        )
        row = await rows.fetchone()
    max_chunk_index = row[0] if row else 0
    is_end = last_selected_index >= max_chunk_index

    # Determine next_cursor
    if is_end:
        next_cursor = None
    else:
        next_index = last_selected_index + 1
        next_cursor = encode_cursor(next_index)

    # --- Build response ---
    content = "\n\n".join(c[2] for c in selected_chunks)
    first = selected_chunks[0]
    last = selected_chunks[-1]

    def _make_position(row) -> ChunkPosition:
        return ChunkPosition(
            page_no=row[3],
            heading_breadcrumb=row[4] or "",
            element_type=row[5] or "PARAGRAPH",
            element_index_on_page=row[6],
            chunk_index=row[1],
        )

    return ReadOutput(
        doc_id=doc_id,
        doc_title=doc_title,
        content=content,
        chunks_returned=len(selected_chunks),
        position_start=_make_position(first),
        position_end=_make_position(last),
        next_cursor=next_cursor,
        is_end_of_document=is_end,
        mode_used=mode,
    ).model_dump()
