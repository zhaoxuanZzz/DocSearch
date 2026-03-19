"""T045: Markdown-aware chunker with table boundary detection.

Algorithm (R4):
1. Parse heading tree to define section boundaries
2. Detect table boundaries (```table-markdown blocks≥)
3. Small tables (≤ CHUNK_MAX_TOKENS): single chunk
4. Large tables: split by row, each sub-chunk prefixed with header row
5. Non-table content: sliding window by semantic boundary (paragraph/sentence)

Each output Chunk carries full position metadata from the ElementMeta list.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.config import settings
from src.ingestion.converter import ConversionResult, ElementMeta

logger = logging.getLogger(__name__)

_APPROX_CHARS_PER_TOKEN = 4


def _token_count(text: str) -> int:
    return max(1, len(text) // _APPROX_CHARS_PER_TOKEN)


@dataclass
class Chunk:
    content: str
    chunk_index: int
    # Position metadata
    page_no: int | None = None
    bbox: dict | None = None
    heading_breadcrumb: str = ""
    element_type: str = "PARAGRAPH"
    element_index_on_page: int | None = None
    markdown_line_start: int = 0
    markdown_line_end: int = 0
    chunk_type: str = "text"  # text | table | table_part
    has_table_header: bool = False


def chunk_document(conversion: ConversionResult) -> list[Chunk]:
    """Split a converted document into Chunks respecting table boundaries."""
    max_tokens = settings.chunk_max_tokens
    chunks: list[Chunk] = []
    idx = 0

    i = 0
    elements = conversion.elements
    while i < len(elements):
        elem = elements[i]

        if elem.element_type == "TABLE":
            new_chunks, advance = _handle_table(elem, idx, max_tokens)
            chunks.extend(new_chunks)
            idx += len(new_chunks)
            i += advance
        else:
            # Accumulate non-table elements into a sliding window
            window_text = elem.text
            window_elems = [elem]
            j = i + 1
            while j < len(elements) and elements[j].element_type not in ("TABLE", "SECTION_HEADER"):
                candidate = window_text + "\n\n" + elements[j].text
                if _token_count(candidate) > max_tokens:
                    break
                window_text = candidate
                window_elems.append(elements[j])
                j += 1

            if window_text.strip():
                first = window_elems[0]
                last = window_elems[-1]
                chunks.append(
                    Chunk(
                        content=window_text,
                        chunk_index=idx,
                        page_no=first.page_no,
                        bbox=first.bbox,
                        heading_breadcrumb=first.heading_breadcrumb,
                        element_type=first.element_type,
                        element_index_on_page=first.element_index_on_page,
                        markdown_line_start=first.markdown_line_start,
                        markdown_line_end=last.markdown_line_end,
                        chunk_type="text",
                    )
                )
                idx += 1

            i = j

    return chunks


def _handle_table(
    table_elem: ElementMeta, start_idx: int, max_tokens: int
) -> tuple[list[Chunk], int]:
    """Return (list_of_chunks, number_of_elements_consumed)."""
    content = table_elem.text

    if _token_count(content) <= max_tokens:
        # Small table: single chunk
        return [
            Chunk(
                content=content,
                chunk_index=start_idx,
                page_no=table_elem.page_no,
                bbox=table_elem.bbox,
                heading_breadcrumb=table_elem.heading_breadcrumb,
                element_type="TABLE",
                element_index_on_page=table_elem.element_index_on_page,
                markdown_line_start=table_elem.markdown_line_start,
                markdown_line_end=table_elem.markdown_line_end,
                chunk_type="table",
            )
        ], 1

    # Large table: split by rows, keep header in each sub-chunk
    rows = content.splitlines()
    header_rows: list[str] = []
    data_rows: list[str] = []
    in_header = True
    for row in rows:
        stripped = row.strip()
        if in_header and (not stripped or set(stripped.replace("|", "").replace("-", "").replace(":", "").replace(" ", "")) == set()):
            # Separator line
            header_rows.append(row)
            in_header = False
        elif in_header:
            header_rows.append(row)
        else:
            data_rows.append(row)

    header_text = "\n".join(header_rows)
    chunks: list[Chunk] = []
    current_rows: list[str] = []
    current_tokens = _token_count(header_text)
    chunk_idx = start_idx

    for row in data_rows:
        rc = _token_count(row)
        if current_tokens + rc > max_tokens and current_rows:
            part_text = header_text + "\n" + "\n".join(current_rows)
            chunks.append(
                Chunk(
                    content=part_text,
                    chunk_index=chunk_idx,
                    page_no=table_elem.page_no,
                    bbox=table_elem.bbox,
                    heading_breadcrumb=table_elem.heading_breadcrumb,
                    element_type="TABLE_PART",
                    element_index_on_page=table_elem.element_index_on_page,
                    markdown_line_start=table_elem.markdown_line_start,
                    markdown_line_end=table_elem.markdown_line_end,
                    chunk_type="table_part",
                    has_table_header=True,
                )
            )
            chunk_idx += 1
            current_rows = [row]
            current_tokens = _token_count(header_text) + rc
        else:
            current_rows.append(row)
            current_tokens += rc

    if current_rows:
        part_text = header_text + "\n" + "\n".join(current_rows)
        chunks.append(
            Chunk(
                content=part_text,
                chunk_index=chunk_idx,
                page_no=table_elem.page_no,
                bbox=table_elem.bbox,
                heading_breadcrumb=table_elem.heading_breadcrumb,
                element_type="TABLE_PART",
                element_index_on_page=table_elem.element_index_on_page,
                markdown_line_start=table_elem.markdown_line_start,
                markdown_line_end=table_elem.markdown_line_end,
                chunk_type="table_part",
                has_table_header=True,
            )
        )

    return chunks or [
        Chunk(
            content=content[:max_tokens * _APPROX_CHARS_PER_TOKEN],
            chunk_index=start_idx,
            page_no=table_elem.page_no,
            heading_breadcrumb=table_elem.heading_breadcrumb,
            element_type="TABLE",
            markdown_line_start=table_elem.markdown_line_start,
            markdown_line_end=table_elem.markdown_line_end,
            chunk_type="table",
        )
    ], 1
