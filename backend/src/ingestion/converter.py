"""T044: Docling-based document converter.

Converts PDF/DOCX to Markdown while preserving rich position metadata
(page_no, bbox, heading_breadcrumb, element_type) for each content element.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ElementMeta:
    """Position metadata for one content element after Docling conversion."""
    text: str
    page_no: int | None = None
    bbox: dict | None = None  # {l, t, r, b} normalised 0-1
    heading_breadcrumb: str = ""
    element_type: str = "PARAGRAPH"  # PARAGRAPH|TABLE|SECTION_HEADER|LIST_ITEM
    element_index_on_page: int | None = None
    markdown_line_start: int = 0
    markdown_line_end: int = 0


@dataclass
class ConversionResult:
    markdown: str
    elements: list[ElementMeta] = field(default_factory=list)


def _build_breadcrumb(heading_stack: list[str]) -> str:
    return " > ".join(heading_stack) if heading_stack else ""


def convert_document(file_path: str | Path) -> ConversionResult:
    """Convert a document file to Markdown with element metadata.

    Supports PDF and DOCX via Docling.  Falls back to plain text extraction
    for unsupported formats.
    """
    path = Path(file_path)
    fmt = path.suffix.lstrip(".").lower()

    if fmt in ("pdf", "docx", "doc"):
        return _convert_with_docling(path)
    elif fmt in ("txt", "md"):
        return _convert_text(path)
    else:
        logger.warning("Unsupported format %s, attempting plain text.", fmt)
        return _convert_text(path)


def _convert_with_docling(path: Path) -> ConversionResult:
    """Use Docling to convert PDF/DOCX with structural metadata."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        logger.error("Docling not installed; falling back to plain text conversion.")
        return _convert_text(path)

    converter = DocumentConverter()
    result = converter.convert(str(path))
    doc = result.document

    elements: list[ElementMeta] = []
    md_lines: list[str] = []
    heading_stack: list[str] = []
    page_element_counts: dict[int, int] = {}

    for item, level in doc.iterate_items():
        text = ""
        etype = "PARAGRAPH"
        pno: int | None = None
        bbox: dict | None = None

        # Extract provenance
        if hasattr(item, "prov") and item.prov:
            prov = item.prov[0]
            pno = getattr(prov, "page_no", None)
            raw_bbox = getattr(prov, "bbox", None)
            if raw_bbox is not None:
                bbox = {
                    "l": round(float(raw_bbox.l), 4),
                    "t": round(float(raw_bbox.t), 4),
                    "r": round(float(raw_bbox.r), 4),
                    "b": round(float(raw_bbox.b), 4),
                }

        # Determine element type and text
        item_type = type(item).__name__
        if "SectionHeader" in item_type or "Heading" in item_type:
            etype = "SECTION_HEADER"
            text = item.text if hasattr(item, "text") else str(item)
            # Maintain heading stack for breadcrumb
            depth = getattr(item, "level", 1)
            heading_stack = heading_stack[: depth - 1]
            heading_stack.append(text)
            md_lines.append(f"{'#' * depth} {text}")
        elif "Table" in item_type:
            etype = "TABLE"
            try:
                text = item.export_to_markdown()
            except Exception:
                text = "[TABLE]"
            md_lines.append(text)
        elif "ListItem" in item_type:
            etype = "LIST_ITEM"
            text = item.text if hasattr(item, "text") else str(item)
            md_lines.append(f"- {text}")
        else:
            # Paragraph
            text = item.text if hasattr(item, "text") else str(item)
            md_lines.append(text)

        if not text.strip():
            continue

        # Track per-page element index
        page_key = pno or 0
        idx = page_element_counts.get(page_key, 0)
        page_element_counts[page_key] = idx + 1

        line_start = len(md_lines) - 1
        elements.append(
            ElementMeta(
                text=text,
                page_no=pno,
                bbox=bbox,
                heading_breadcrumb=_build_breadcrumb(heading_stack),
                element_type=etype,
                element_index_on_page=idx,
                markdown_line_start=line_start,
                markdown_line_end=line_start,
            )
        )

    markdown = "\n\n".join(line for line in md_lines if line)
    return ConversionResult(markdown=markdown, elements=elements)


def _convert_text(path: Path) -> ConversionResult:
    """Simple plain-text / Markdown pass-through conversion."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.error("Failed to read %s: %s", path, exc)
        text = ""

    lines = text.splitlines()
    elements: list[ElementMeta] = []
    heading_stack: list[str] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            depth = len(stripped) - len(stripped.lstrip("#"))
            heading_text = stripped.lstrip("# ").strip()
            heading_stack = heading_stack[:depth - 1]
            heading_stack.append(heading_text)
            etype = "SECTION_HEADER"
        else:
            etype = "PARAGRAPH"
        elements.append(
            ElementMeta(
                text=stripped,
                page_no=None,
                heading_breadcrumb=_build_breadcrumb(heading_stack),
                element_type=etype,
                element_index_on_page=i,
                markdown_line_start=i,
                markdown_line_end=i,
            )
        )

    return ConversionResult(markdown=text, elements=elements)
