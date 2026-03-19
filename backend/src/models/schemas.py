"""Pydantic schemas for request/response validation."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Shared position metadata
# ---------------------------------------------------------------------------


class ChunkPosition(BaseModel):
    page_no: int | None = None
    heading_breadcrumb: str = Field(default="", description="e.g. '第2章 > 2.3节 > 表2-1'")
    element_type: str = Field(
        default="PARAGRAPH",
        description="PARAGRAPH|TABLE|TABLE_PART|SECTION_HEADER|LIST_ITEM",
    )
    element_index_on_page: int | None = None
    chunk_index: int = Field(description="Sequential index within the document (0-based)")


# ---------------------------------------------------------------------------
# Document schemas
# ---------------------------------------------------------------------------


class DocumentCreate(BaseModel):
    title: str
    file_name: str
    format: str
    file_size: int | None = None


class DocumentResponse(BaseModel):
    id: int
    title: str
    file_name: str
    format: str
    file_size: int | None
    minio_key: str
    markdown_key: str | None
    chunk_count: int
    status: str
    error_message: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class DocumentStatusResponse(BaseModel):
    id: int
    status: str
    chunk_count: int
    error_message: str | None
    progress: int | None = None  # 0-100, from Redis job cache


class DocumentStatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    indexed_documents: int
    processing_documents: int
    pending_documents: int
    failed_documents: int


# ---------------------------------------------------------------------------
# Query skill schemas (contracts/query-skill.md)
# ---------------------------------------------------------------------------


class ContextWindow(BaseModel):
    prev_chunk: ChunkResult | None = None
    next_chunk: ChunkResult | None = None


class ChunkResult(BaseModel):
    chunk_id: int
    document_id: int
    document_title: str
    content: str
    score: float = Field(ge=0.0, le=1.0)
    position: ChunkPosition
    context: ContextWindow | None = None


class QueryInput(BaseModel):
    query: str = Field(description="自然语言查询文本")
    doc_ids: list[int] = Field(default_factory=list, description="限定文档 ID 列表；空列表表示全库检索")
    top_k: int = Field(default=5, ge=1, le=20, description="返回片段数量")
    mode: str = Field(default="hybrid", description="semantic|keyword|hybrid")
    expand_context: bool = Field(default=False)

    @model_validator(mode="after")
    def validate_mode(self) -> QueryInput:
        if self.mode not in ("semantic", "keyword", "hybrid"):
            raise ValueError(f"mode must be one of: semantic, keyword, hybrid. Got: {self.mode}")
        return self


class QueryOutput(BaseModel):
    results: list[ChunkResult]
    total_found: int
    strategy_used: str
    query_truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0
    # Observability (FR-025)
    strategy_type: str = "hybrid"
    strategy_reason: str = ""


# ---------------------------------------------------------------------------
# Read skill schemas (contracts/read-skill.md)
# ---------------------------------------------------------------------------


class ReadInput(BaseModel):
    doc_id: int = Field(description="文档 ID")
    start_page: int | None = Field(default=None, ge=1)
    start_breadcrumb: str | None = None
    cursor: str | None = None
    mode: str = Field(default="heading", description="token|heading")
    max_tokens: int = Field(default=2000, ge=1, le=4000)

    @model_validator(mode="after")
    def validate_mode(self) -> ReadInput:
        if self.mode not in ("token", "heading"):
            raise ValueError(f"mode must be 'token' or 'heading'. Got: {self.mode}")
        return self


class ReadOutput(BaseModel):
    doc_id: int
    doc_title: str
    content: str
    chunks_returned: int
    position_start: ChunkPosition
    position_end: ChunkPosition
    next_cursor: str | None
    is_end_of_document: bool
    mode_used: str
    # Observability (FR-025)
    strategy_type: str = "read"
    strategy_reason: str = "Direct sequential read"


# ---------------------------------------------------------------------------
# Grep skill schemas (contracts/grep-skill.md)
# ---------------------------------------------------------------------------


class GrepInput(BaseModel):
    pattern: str = Field(description="正则表达式或关键词")
    doc_ids: list[int] = Field(default_factory=list)
    is_regex: bool = False
    case_sensitive: bool = False
    context_lines: int = Field(default=1, ge=0, le=3)
    max_matches_per_doc: int = Field(default=50, ge=1)


class GrepMatch(BaseModel):
    match_text: str
    line_content: str
    context_before: list[str]
    context_after: list[str]
    position: ChunkPosition
    chunk_id: int


class GrepDocResult(BaseModel):
    document_id: int
    document_title: str
    match_count: int
    truncated: bool
    matches: list[GrepMatch]


class GrepOutput(BaseModel):
    results: list[GrepDocResult]
    total_docs_searched: int
    total_matches: int
    pattern_used: str
    warnings: list[str] = Field(default_factory=list)
    # Observability (FR-025)
    strategy_type: str = "grep"
    strategy_reason: str = "Pattern matching on document full text"


# ---------------------------------------------------------------------------
# Routing advisor schemas (contracts/routing-advisor.md)
# ---------------------------------------------------------------------------


class RoutingRequest(BaseModel):
    doc_ids: list[int] = Field(default_factory=list)
    query_intent: str = Field(
        description="semantic|exact|pattern|sequential"
    )
    query_sample: str | None = None

    @model_validator(mode="after")
    def validate_intent(self) -> RoutingRequest:
        valid = ("semantic", "exact", "pattern", "sequential")
        if self.query_intent not in valid:
            raise ValueError(f"query_intent must be one of: {valid}. Got: {self.query_intent}")
        return self


class DocStats(BaseModel):
    total_docs: int
    total_chunks: int
    total_size_bytes: int
    indexed_docs: int
    unindexed_docs: int


class ThresholdInfo(BaseModel):
    small_doc_threshold: int
    small_size_threshold_mb: float
    low_confidence_score_threshold: float = 0.5


class RoutingResponse(BaseModel):
    recommended_skill: str
    fallback_skill: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    doc_stats: DocStats
    thresholds_applied: ThresholdInfo
    low_confidence_note: str | None = None
