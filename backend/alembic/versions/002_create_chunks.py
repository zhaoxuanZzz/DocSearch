"""Create chunks table with pgvector embedding and BM25 indexes.

Revision ID: 002
Revises: 001
Create Date: 2026-03-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable required extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=True),
        # pgvector column – stored as text here; actual type managed by the extension
        sa.Column("embedding", sa.Text(), nullable=True),  # overridden below
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("chunk_type", sa.Text(), nullable=False, server_default="text"),
        sa.Column("has_table_header", sa.Boolean(), nullable=False, server_default="false"),
        # Position metadata
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("heading_breadcrumb", sa.Text(), nullable=True),
        sa.Column("element_type", sa.Text(), nullable=True),
        sa.Column("element_index_on_page", sa.Integer(), nullable=True),
        sa.Column("markdown_line_start", sa.Integer(), nullable=True),
        sa.Column("markdown_line_end", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Replace the placeholder text column with the real vector type
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024) USING NULL")
    op.execute("ALTER TABLE chunks ALTER COLUMN bbox TYPE jsonb USING bbox::jsonb")

    # Standard indexes
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_document_chunk", "chunks", ["document_id", "chunk_index"])
    op.create_index("ix_chunks_page_no", "chunks", ["page_no"])

    # HNSW vector index (pgvector)
    op.execute(
        """
        CREATE INDEX ix_chunks_embedding_hnsw ON chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # BM25 full-text index (ParadeDB pg_search)
    op.execute(
        """
        CREATE INDEX ix_chunks_bm25 ON chunks
        USING bm25 (id, content, heading_breadcrumb)
        WITH (key_field = 'id')
        """
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_bm25", table_name="chunks")
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.drop_index("ix_chunks_page_no", table_name="chunks")
    op.drop_index("ix_chunks_document_chunk", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
