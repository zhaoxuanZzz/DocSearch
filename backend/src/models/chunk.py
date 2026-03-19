"""SQLAlchemy ORM model for the chunks table."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db import Base


class Chunk(Base):
    __tablename__ = "chunks"

    # chunk_type constants
    TYPE_TEXT = "text"
    TYPE_TABLE = "table"
    TYPE_TABLE_PART = "table_part"
    TYPE_TITLE = "title"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list | None] = mapped_column(Vector(1024), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # chunk type / table metadata
    chunk_type: Mapped[str] = mapped_column(Text, nullable=False, default=TYPE_TEXT)
    has_table_header: Mapped[bool] = mapped_column(Boolean, default=False)

    # Position metadata (from Docling)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    bbox: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    heading_breadcrumb: Mapped[str | None] = mapped_column(Text, nullable=True)
    element_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    element_index_on_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    markdown_line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    markdown_line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationship back to document
    document: Mapped["Document"] = relationship(  # noqa: F821
        "Document", back_populates="chunks"
    )
