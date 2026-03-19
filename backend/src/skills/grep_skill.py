"""T027: grep_documents LangChain tool.

Performs regex/keyword search over full Markdown text of indexed documents.
Downloads Markdown from MinIO for each target document, runs Python `re` matching.
"""

from __future__ import annotations

import logging
import re

from langchain_core.tools import tool

from src.core.config import settings
from src.core.db import get_pool
from src.models.schemas import GrepDocResult, GrepInput, GrepMatch, GrepOutput
from src.storage.minio_client import MinioClient

logger = logging.getLogger(__name__)


def _find_chunk_for_line(
    line_no: int, chunk_boundaries: list[tuple[int, int, dict]]
) -> dict | None:
    """Return the chunk metadata dict that covers the given 1-based line number."""
    for start, end, meta in chunk_boundaries:
        if start <= line_no <= end:
            return meta
    return None


@tool(args_schema=GrepInput)
async def grep_documents(
    pattern: str,
    doc_ids: list[int] | None = None,
    is_regex: bool = False,
    case_sensitive: bool = False,
    context_lines: int = 1,
    max_matches_per_doc: int = 50,
) -> dict:
    """T027: Full-text grep over indexed documents using Python regex.

    Returns matches with surrounding context lines and precise chunk positions.
    """
    context_lines = min(context_lines, 3)

    if not pattern.strip():
        raise ValueError("PATTERN_EMPTY: pattern must not be empty")

    # Validate regex early
    if is_regex:
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            compiled = re.compile(pattern, flags)
        except re.error as exc:
            raise ValueError(f"INVALID_PATTERN: {exc}") from exc
    else:
        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(re.escape(pattern), flags)

    pool = await get_pool()
    minio = MinioClient()

    # --- Resolve document IDs ---
    if doc_ids:
        doc_id_list = doc_ids
    else:
        async with pool.connection() as conn:
            rows = await conn.execute("SELECT id FROM documents WHERE status = 'indexed'")
            doc_id_list = [row[0] async for row in rows]

    if not doc_id_list:
        raise ValueError("NO_DOCS_FOUND: no indexed documents found")

    # Check doc_limit
    if len(doc_id_list) > settings.grep_doc_limit:
        raise ValueError(
            f"DOC_LIMIT_EXCEEDED: requested {len(doc_id_list)} docs, "
            f"max allowed is {settings.grep_doc_limit}"
        )

    # Validate all doc_ids exist and are indexed
    async with pool.connection() as conn:
        rows = await conn.execute(
            "SELECT id, title, status, file_name FROM documents WHERE id = ANY(%s)",
            (doc_id_list,),
        )
        doc_meta = {row[0]: {"title": row[1], "status": row[2], "file_name": row[3]} async for row in rows}

    not_indexed = [str(d) for d in doc_id_list if doc_meta.get(d, {}).get("status") != "indexed"]
    if not_indexed:
        raise ValueError(
            f"DOCS_NOT_INDEXED: the following documents are not ready: {', '.join(not_indexed)}"
        )

    # --- Fetch chunk boundary metadata for position mapping ---
    async with pool.connection() as conn:
        rows = await conn.execute(
            """
            SELECT c.id, c.document_id, c.chunk_index, c.markdown_line_start,
                   c.markdown_line_end, c.page_no, c.heading_breadcrumb,
                   c.element_type, c.element_index_on_page
            FROM chunks c
            WHERE c.document_id = ANY(%s)
            ORDER BY c.document_id, c.chunk_index
            """,
            (doc_id_list,),
        )
        chunk_rows_all = [row async for row in rows]

    # Group chunk boundaries by document_id
    chunk_map: dict[int, list[tuple[int, int, dict]]] = {}
    for row in chunk_rows_all:
        cid, did, cidx, lstart, lend, pno, breadcrumb, etype, eidx = row
        chunk_map.setdefault(did, []).append(
            (
                lstart or 0,
                lend or 0,
                {
                    "chunk_id": cid,
                    "chunk_index": cidx,
                    "page_no": pno,
                    "heading_breadcrumb": breadcrumb or "",
                    "element_type": etype or "PARAGRAPH",
                    "element_index_on_page": eidx,
                },
            )
        )

    # --- Process each document ---
    grep_results: list[GrepDocResult] = []
    total_matches = 0
    warnings: list[str] = []

    for doc_id in doc_id_list:
        meta = doc_meta[doc_id]
        try:
            md_bytes = minio.download_markdown(doc_id)
            md_text = md_bytes.decode("utf-8") if isinstance(md_bytes, bytes) else md_bytes
        except Exception as exc:
            warnings.append(f"Document {doc_id}: failed to download markdown: {exc}")
            continue

        lines = md_text.splitlines()
        boundaries = chunk_map.get(doc_id, [])

        matches: list[GrepMatch] = []
        truncated = False

        for line_no, line in enumerate(lines, start=1):
            for m in compiled.finditer(line):
                if len(matches) >= max_matches_per_doc:
                    truncated = True
                    break

                before = lines[max(0, line_no - 1 - context_lines) : line_no - 1]
                after = lines[line_no : min(len(lines), line_no + context_lines)]

                chunk_meta = _find_chunk_for_line(line_no, boundaries)
                if chunk_meta is None:
                    # Fallback: use first chunk of document
                    chunk_meta = boundaries[0][2] if boundaries else {
                        "chunk_id": 0, "chunk_index": 0, "page_no": None,
                        "heading_breadcrumb": "", "element_type": "PARAGRAPH",
                        "element_index_on_page": None,
                    }

                from src.models.schemas import ChunkPosition

                matches.append(
                    GrepMatch(
                        match_text=m.group(0),
                        line_content=line,
                        context_before=before,
                        context_after=after,
                        position=ChunkPosition(
                            page_no=chunk_meta["page_no"],
                            heading_breadcrumb=chunk_meta["heading_breadcrumb"],
                            element_type=chunk_meta["element_type"],
                            element_index_on_page=chunk_meta["element_index_on_page"],
                            chunk_index=chunk_meta["chunk_index"],
                        ),
                        chunk_id=str(chunk_meta["chunk_id"]),
                    )
                )
            if truncated:
                break

        grep_results.append(
            GrepDocResult(
                document_id=str(doc_id),
                document_title=meta["title"],
                match_count=len(matches),
                truncated=truncated,
                matches=matches,
            )
        )
        total_matches += len(matches)

    return GrepOutput(
        results=grep_results,
        total_docs_searched=len(doc_id_list),
        total_matches=total_matches,
        pattern_used=pattern,
        warnings=warnings,
    ).model_dump()
