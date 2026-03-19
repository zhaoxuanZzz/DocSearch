# Data Model: Agent 文档检索与 RAG 增强系统

**Branch**: `001-agent-doc-rag-retrieval` | **Date**: 2026-03-17

---

## Entity Overview

```
┌──────────────┐   1:N   ┌──────────────┐   1:1   ┌──────────────┐
│   Document   │────────▶│    Chunk     │────────▶│  Embedding   │
│  (文档元数据) │         │  (文档片段)   │         │   (向量)     │
└──────────────┘         └──────────────┘         └──────────────┘
       │                        │
       │ MinIO Object            │ LocationMetadata
       ▼                        ▼
┌──────────────┐         ┌──────────────┐
│  FileStore   │         │  PositionRef │
│ (原始+MD文件) │         │ (页码+路径)   │
└──────────────┘         └──────────────┘

┌──────────────┐
│ RoutingHint  │   (无状态，按请求生成，不持久化)
│  (路由建议)   │
└──────────────┘
```

---

## 核心实体定义

### Document（文档）

文档库中的一份原始文件，是整个系统的顶层数据单元。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | PK | 自增主键 |
| `title` | TEXT | NOT NULL | 文档标题（可来自文件名或元数据） |
| `file_name` | TEXT | NOT NULL | 原始文件名（含扩展名） |
| `file_size` | BIGINT | | 原始文件字节数 |
| `format` | TEXT | NOT NULL | `pdf` / `docx` / `md` / `txt` |
| `minio_key` | TEXT | NOT NULL, UNIQUE | MinIO 原始文件对象路径 |
| `markdown_key` | TEXT | | MinIO Markdown 对象路径（PDF/DOCX 转换后） |
| `chunk_count` | INT | DEFAULT 0 | 当前已索引 Chunk 数量 |
| `status` | TEXT | NOT NULL | `pending` / `processing` / `indexed` / `failed` |
| `error_message` | TEXT | NULLABLE | 处理失败时的错误信息 |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | 上传时间 |
| `updated_at` | TIMESTAMPTZ | DEFAULT NOW() | 最近更新时间（含状态变更） |

**索引**:
- PK(`id`)
- UNIQUE(`minio_key`)
- INDEX(`status`) — 快速查询待处理文档
- INDEX(`created_at` DESC) — 文档列表排序

**状态转换**:
```
pending ──► processing ──► indexed
                  └──────► failed
indexed ──► processing  (文档更新时)
```

---

### Chunk（文档片段）

文档经分块处理后的最小检索单元，携带完整位置元数据。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | BIGSERIAL | PK | 自增主键 |
| `document_id` | BIGINT | FK → documents(id) CASCADE | 所属文档 |
| `chunk_index` | INT | NOT NULL | 在文档中的顺序（0-based） |
| `content` | TEXT | NOT NULL | 片段文本内容 |
| `content_hash` | TEXT | | SHA256，用于去重 |
| `embedding` | vector(1024) | | 语义向量（维度依模型而定） |
| `token_count` | INT | | 估算 token 数 |
| `chunk_type` | TEXT | NOT NULL | `text` / `table` / `table_part` / `title` |
| `has_table_header` | BOOLEAN | DEFAULT FALSE | 该 Chunk 是否含表头行（table_part 时使用） |
| **位置元数据** | | | |
| `page_no` | INT | | 页码（1-based） |
| `bbox` | JSONB | | 页面坐标 `{l, r, t, b}` |
| `heading_breadcrumb` | TEXT | | 标题路径，如 `"第2章 > 2.3节 > 表2-1"` |
| `element_type` | TEXT | | Docling 元素类型：`PARAGRAPH` / `TABLE` / `SECTION_HEADER` / `LIST_ITEM` |
| `element_index_on_page` | INT | | 在所在页面内的元素顺序索引（0-based） |
| `markdown_line_start` | INT | | 在转换后 Markdown 文件中的起始行号 |
| `markdown_line_end` | INT | | 在转换后 Markdown 文件中的结束行号 |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() | 创建时间 |

**索引**:
- PK(`id`)
- INDEX(`document_id`) — 按文档过滤
- INDEX(`document_id`, `chunk_index`) — 顺序阅读 (`read` 技能)
- INDEX(`page_no`) — 按页定位
- HNSW INDEX(`embedding` vector_cosine_ops, m=16, ef_construction=64) — 向量检索
- BM25 INDEX(`content`, `heading_breadcrumb`) via ParadeDB pg_search — 关键词检索

**业务规则**:
- `table_part` 类型的 Chunk 必须 `has_table_header = TRUE`（每个分割块携带表头）
- `markdown_line_start`/`markdown_line_end` 仅当原始格式为 PDF/DOCX 时填充
- `chunk_index` 在同一 `document_id` 内唯一且连续，支持 `read` 技能的翻页导航

---

### IndexingJob（索引任务）

跟踪 Celery 异步任务的执行状态（轻量化，非必须持久化，可用 Redis 替代）。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | TEXT | PK | Celery task_id（UUID） |
| `document_id` | BIGINT | FK → documents(id) | 关联文档 |
| `stage` | TEXT | NOT NULL | `converting` / `chunking` / `embedding` / `indexing` |
| `progress` | INT | DEFAULT 0 | 进度百分比 0-100 |
| `error` | TEXT | NULLABLE | 错误详情 |
| `started_at` | TIMESTAMPTZ | | 任务开始时间 |
| `finished_at` | TIMESTAMPTZ | NULLABLE | 任务完成时间 |

> **注**: 该实体优先存储在 Redis（TTL 1 小时），仅在需要历史审计时写入 PostgreSQL。

---

### RoutingHint（路由建议）— 无状态

路由建议仅按请求计算，不持久化，通过 Redis 缓存短暂保存。

| 字段 | 类型 | 说明 |
|------|------|------|
| `recommended_skill` | TEXT | `query` / `read` / `grep` |
| `reason` | TEXT | 推荐理由（人类可读） |
| `doc_count` | INT | 目标文档数量 |
| `total_size_bytes` | BIGINT | 目标文档总体积 |
| `confidence` | FLOAT | 0.0–1.0，推荐置信度 |
| `fallback_skill` | TEXT | 若主策略失败时的备选技能 |

---

## 文件存储模型（MinIO）

```
Bucket: docsearch
│
├── originals/
│   └── {document_id}/{file_name}          ← 原始上传文件
│
├── markdown/
│   └── {document_id}/converted.md         ← Docling 转换结果（PDF/DOCX only）
│
└── temp/
    └── {upload_token}/{file_name}          ← 上传中间状态（TTL 1小时）
```

对象命名规则：`{document_id}` 为 PostgreSQL 自增 ID 的字符串形式，确保唯一性和可追溯性。

---

## 缓存模型（Redis）

| Key Pattern | TTL | 内容 |
|-------------|-----|------|
| `query:{query_hash}:{doc_ids_hash}:{mode}` | 5 min | 序列化的 RetrievalResult JSON |
| `doc:status:{document_id}` | 10 min | 文档索引状态字符串 |
| `routing:{doc_count}:{total_size_kb}:{intent_hash}` | 1 min | RoutingHint JSON |
| `job:{task_id}` | 1 hour | IndexingJob 状态 JSON |
| `doc:meta:{document_id}` | 30 min | 文档元数据（用于 `read`/`grep` 前置校验） |

---

## 数据流图

### 文档摄入流

```
上传文件
   │
   ▼
[MinIO] 存储原始文件
   │ 触发 Celery 任务
   ▼
[Docling] PDF/DOCX → Markdown（保留位置元数据）
   │
   ├── [MinIO] 存储 Markdown 版本
   │
   ▼
[Chunker] Markdown → Chunks（表格感知分块）
   │
   ▼
[Embedder] Chunk.content → vector(1024)
   │
   ▼
[PostgreSQL] 写入 chunks 表（含 embedding + 位置元数据）
   │
   ▼
[BM25 Index] ParadeDB 自动更新 BM25 索引
   │
   ▼
documents.status = "indexed"
[Redis] 清除相关查询缓存
```

### query 技能数据流

```
Agent 调用 query(query, doc_ids, top_k, mode)
   │
   ├── [Redis] 命中缓存 → 直接返回
   │
   ▼
[PostgreSQL pgvector] 向量检索 Top-20
[PostgreSQL pg_search] BM25 检索 Top-20
   │
   ▼
[RRF 融合] → Top-20 候选
   │
   ▼
[Cross-encoder Reranker] → Top-K 最终结果
   │
   ▼
[Context Expander] 可选：扩展相邻 Chunk
   │
   ▼
[Redis] 写入缓存
   │
   ▼
返回 RetrievalResult（含精准位置元数据）
```

### read 技能数据流

```
Agent 调用 read(doc_id, position, mode)
   │
   ▼
[PostgreSQL] 查询 chunks WHERE document_id=? ORDER BY chunk_index
  按 position（页码 或 heading_breadcrumb 前缀）定位起始 Chunk
   │
   ▼
按 mode 返回内容：
  - token_mode：累积 Chunk 直至达到 token 上限
  - heading_mode：返回同一标题块下的所有 Chunk
   │
   ▼
返回内容 + 下一页 cursor（next_chunk_index）
```

---

## 实体关系（ER 简图）

```
documents ──< chunks
   1            N
   │
   └── minio_key (原始文件)
   └── markdown_key (转换后)

chunks.embedding → pgvector HNSW 索引
chunks.content   → pg_search BM25 索引
```

---

## 验证规则

| 规则 | 描述 |
|------|------|
| `chunk_index` 连续性 | 同一文档的 chunk_index 必须连续，不允许空洞 |
| `table_part` 一致性 | `chunk_type=table_part` 时 `has_table_header` 必须为 TRUE |
| `embedding` 维度 | 所有 embedding 向量维度必须一致（由配置文件约束） |
| 孤立 Chunk 防止 | `document_id` 外键 CASCADE DELETE，删除文档时自动清除所有 Chunk |
| 状态流转单向性 | `indexed` 状态不可直接回退至 `pending`，更新须经 `processing` 状态 |
