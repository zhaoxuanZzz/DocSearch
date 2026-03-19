# Research: Agent 文档检索与 RAG 增强系统

**Branch**: `001-agent-doc-rag-retrieval` | **Date**: 2026-03-17  
**Status**: Complete — 所有 NEEDS CLARIFICATION 项已解决

---

## R1 — DeepAgents 工具/技能定义模式

**Decision**: 使用 LangChain `@tool` 装饰器 + Pydantic `args_schema` 定义三种文档技能

**Rationale**: DeepAgents 基于 LangChain + LangGraph 构建，工具定义直接使用 LangChain 标准模式。Pydantic args_schema 提供严格类型校验，类型提示自动生成 LLM 可见的 JSON Schema。DeepAgents 通过 `subagents` 机制支持多 Agent 路由，主 Agent 通过 `task()` 工具自主委派子任务，无需手动路由逻辑。

**Alternatives considered**:
- 纯函数工具（无 Pydantic）：类型描述弱，LLM 调用易出错，排除
- 自研 Agent 框架：成本高，无此必要，排除

**Key pattern**:
```python
from langchain.tools import tool
from pydantic import BaseModel, Field

class QueryInput(BaseModel):
    query: str = Field(description="自然语言查询文本")
    doc_ids: list[str] = Field(default=[], description="限定文档集，空列表表示全库")
    top_k: int = Field(default=5, description="返回片段数量")
    mode: str = Field(default="hybrid", description="检索模式: semantic|keyword|hybrid")

@tool(args_schema=QueryInput)
async def query_documents(query: str, doc_ids: list, top_k: int, mode: str) -> dict:
    """在文档库中执行语义+关键词混合检索，返回相关片段及精准位置元数据"""
    ...
```

FastAPI 集成通过 LangServe 的 `add_routes()` 暴露 `/invoke`、`/stream` 端点。

---

## R2 — Docling 文档转换与位置元数据

**Decision**: 使用 `DoclingDocument.iterate_items()` 遍历文档树，通过 `ProvenanceItem` 提取位置，通过 `parent` 指针链构建 Heading Breadcrumb

**Rationale**: Docling 原生保留每个元素（段落/表格/标题）的完整位置信息：页码（`prov.page_no`）、坐标（`prov.bbox`）、元素类型（`label`）、字符偏移（`charspan`）。通过向上遍历 `parent` 指针链可重建 "章节 > 小节 > 元素" 路径。统一数据模型同时覆盖 PDF 和 DOCX。

**Alternatives considered**:
- PyMuPDF：坐标精确，但无语义结构（无标题层级），排除
- pdfplumber：擅长表格，但无 heading hierarchy，排除
- 视觉模型（LLaVA等）：位置不稳定，推理成本高，排除

**Key data model**:
```python
# 每个 DocItem 携带的关键字段
element.label          # DocItemLabel: PARAGRAPH / TABLE / SECTION_HEADER / TITLE
element.prov[0].page_no    # 页码 (1-indexed)
element.prov[0].bbox       # BoundingBox(l, r, t, b)
element.prov[0].charspan   # (start, end) 字符偏移
element.parent             # JSON Pointer → 父元素（用于 breadcrumb 构建）

# TableItem 额外字段
table.data.grid            # List[List[TableCell]]
cell.row_span, cell.col_span    # 合并单元格
cell.column_header         # 是否为表头行
table.export_to_markdown() # 生成标准 Markdown 表格
```

**Breadcrumb 构建算法**:
```python
def build_breadcrumb(doc: DoclingDocument, item: DocItem) -> str:
    parts = []
    ref = item.parent
    while ref:
        parent = ref.resolve(doc)
        if isinstance(parent, SectionHeaderItem):
            parts.insert(0, parent.text)
        ref = getattr(parent, 'parent', None)
    return " > ".join(parts)
```

**位置元数据存储结构**（每个 Chunk 携带）:
```json
{
  "page_no": 3,
  "bbox": [72.0, 540.0, 100.0, 720.0],
  "heading_breadcrumb": "第2章 安装指南 > 2.3 环境配置 > 表2-1",
  "element_type": "TABLE",
  "element_index_on_page": 2,
  "markdown_line_start": 145,
  "markdown_line_end": 162
}
```

---

## R3 — PostgreSQL + pgvector 混合检索架构

**Decision**: HNSW 向量索引（pgvector）+ ParadeDB `pg_search` BM25 索引 + RRF（Reciprocal Rank Fusion）结果融合

**Rationale**:
- HNSW 优于 IVFFlat：无需预训练，高召回率，生产环境首选；100k chunks @ 50 QPS 实测 p95 约 50-70ms
- ParadeDB `pg_search` 实现真正的 BM25（非 ts_rank/TF-IDF），原生 PostgreSQL，无需额外服务
- RRF 优于线性加权：不受向量分数（0-1）与 BM25 分数（无界）的量纲差异影响，排名更稳定

**Alternatives considered**:
- Elasticsearch + pgvector：双栈运维复杂度高，排除
- ts_rank + tsvector：TF-IDF 非 BM25，排名质量差，排除
- Qdrant / Weaviate：额外组件，用户要求全用 PostgreSQL，排除

**Key schema**:
```sql
-- 文档表
CREATE TABLE documents (
  id          BIGSERIAL PRIMARY KEY,
  title       TEXT NOT NULL,
  file_name   TEXT NOT NULL,
  file_size   BIGINT,
  format      TEXT,               -- pdf|docx|md|txt
  minio_key   TEXT NOT NULL,      -- MinIO 原始文件路径
  markdown_key TEXT,              -- MinIO Markdown 路径（Docling 转换后）
  chunk_count INT DEFAULT 0,
  status      TEXT DEFAULT 'pending', -- pending|processing|indexed|failed
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 分块表
CREATE TABLE chunks (
  id              BIGSERIAL PRIMARY KEY,
  document_id     BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index     INT NOT NULL,
  content         TEXT NOT NULL,
  content_hash    TEXT,           -- SHA256，去重用
  embedding       vector(1024),  -- 向量维度依模型定
  -- 位置元数据（来自 Docling）
  page_no         INT,
  bbox            JSONB,
  heading_breadcrumb TEXT,
  element_type    TEXT,           -- paragraph|table|title|list_item
  element_index_on_page INT,
  markdown_line_start INT,
  markdown_line_end   INT,
  chunk_type      TEXT DEFAULT 'text', -- text|table|table_part
  has_table_header BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 向量索引（HNSW）
CREATE INDEX chunks_embedding_hnsw ON chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- BM25 全文索引
CREATE INDEX chunks_bm25 ON chunks
  USING bm25 (id, content, heading_breadcrumb)
  WITH (key_field = 'id');

-- 文档过滤索引
CREATE INDEX ON chunks (document_id);
CREATE INDEX ON chunks (page_no);
```

**RRF 混合查询模式**:
```sql
WITH vector_ranked AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY embedding <=> $query_vec) AS rank
  FROM chunks WHERE document_id = ANY($doc_ids)
  LIMIT 20
),
bm25_ranked AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY rank DESC) AS rank
  FROM chunks WHERE content @@@ $query_text
    AND document_id = ANY($doc_ids)
  LIMIT 20
),
rrf AS (
  SELECT COALESCE(v.id, b.id) AS id,
    COALESCE(1.0/(60+v.rank), 0) + COALESCE(1.0/(60+b.rank), 0) AS score
  FROM vector_ranked v
  FULL OUTER JOIN bm25_ranked b ON v.id = b.id
)
SELECT c.*, r.score FROM rrf r JOIN chunks c ON c.id = r.id
ORDER BY r.score DESC LIMIT $top_k;
```

**性能调优参数**（100k chunks, 50 QPS）:
```
hnsw.ef_search = 100
shared_buffers = 4GB (若 16GB RAM)
work_mem = 256MB
max_parallel_workers_per_gather = 4
```

---

## R4 — Markdown 表格感知分块策略

**Decision**: 三阶段分块策略：解析标题树 → 检测表格边界 → 按语义单元分块（整表/行分割+保头）

**Rationale**:
- 表格内容是 RAG 中最易被破坏的结构：跨行截断导致语义丢失或含义反转
- Docling 已将表格转为结构化 Markdown，可以精确检测表格起止行
- 小表（整体 ≤ 512 token）作为单 Chunk 最优，保留完整语义
- 大表按完整行边界分割，每个子 Chunk 携带表头行（确保 LLM 能解读列含义）

**Key algorithm**（伪代码）:
```python
CHUNK_MAX_TOKENS = 512
TABLE_HEADER_ROWS = 1  # 默认首行为表头

def chunk_markdown(md: str, metadata: dict) -> list[Chunk]:
    blocks = split_by_heading_and_table_boundary(md)
    chunks = []
    for block in blocks:
        if block.type == "table":
            header = block.rows[0]
            remaining = block.rows[1:]
            current = [header]
            for row in remaining:
                if token_count(current + [row]) > CHUNK_MAX_TOKENS:
                    chunks.append(Chunk(rows=current, type="table_part", has_header=True, **metadata))
                    current = [header, row]  # 新子块重新携带表头
                else:
                    current.append(row)
            chunks.append(Chunk(rows=current, type="table_part" if len(current)>2 else "table", **metadata))
        else:
            # 段落/标题：按 token 长度滑动分块，保持句子边界
            chunks.extend(split_text_block(block, max_tokens=CHUNK_MAX_TOKENS))
    return chunks
```

**Alternatives considered**:
- LangChain RecursiveCharacterTextSplitter：无表格感知，排除
- LlamaIndex MarkdownNodeParser：对标题有感知但无表头保留逻辑，排除
- 固定 Token 截断：破坏表格结构，排除

---

## R5 — 检索结果重排序（Reranking）

**Decision**: Cross-encoder 重排序模型作为可选第二阶段（初始召回 Top-20 → 重排序 → 返回 Top-K）

**Rationale**: Cross-encoder 同时编码查询和候选片段，相关性判断远优于 Bi-encoder；仅对初始召回的少量候选（20条）运行，延迟可控（通常 +100-200ms）；可使用轻量开源模型私有化部署。

**Alternatives considered**:
- 纯向量检索无重排序：召回精度受限，特别对专业术语类查询
- LLM 作为 reranker：成本高、延迟不可控，排除用于生产

---

## R6 — Redis 缓存策略

**Decision**: 三层 Redis 缓存：查询结果缓存（TTL 5min）、文档索引状态缓存、路由建议缓存（TTL 1min）

**Rationale**: 对重复查询（相同 query + doc_ids 组合）直接返回缓存，绕过向量检索和重排序，是在高并发下保持 p95 ≤ 2s 的关键手段。Key 以 `query_hash:doc_ids_hash` 构成，确保精确匹配。

---

## Resolution Summary

| NEEDS CLARIFICATION 项 | 解决方案 |
|-------------------------|----------|
| DeepAgents 工具定义模式 | LangChain `@tool` + Pydantic `args_schema`，via LangServe 暴露 API |
| Docling 位置元数据结构 | `ProvenanceItem` (page_no, bbox, charspan) + parent 链 (breadcrumb) |
| PostgreSQL 向量索引类型 | HNSW (`m=16, ef_construction=64`，`ef_search=100`) |
| BM25 实现方式 | ParadeDB `pg_search` 扩展 |
| 混合检索结果融合算法 | RRF (k=60)，SQL WITH 子句实现 |
| Markdown 表格分块 | 整表单 Chunk + 大表按完整行分割保留表头 |
| 多语言支持 | ParadeDB 支持 ICU tokenizer（中文/英文），pgvector 使用多语言嵌入模型（如 `bge-m3`） |
