# Contract: query 技能

**Skill**: `query_documents`  
**FR Reference**: FR-006, FR-007, FR-008, FR-009, FR-010, FR-014, FR-015, FR-019  
**Version**: 1.0

---

## 功能描述

在指定文档集（或全库）内执行语义 + 关键词混合召回，通过 RRF 融合和 Cross-encoder 重排序，返回 Top-K 最相关文档片段及精准原文位置信息。

---

## 输入 Schema

```typescript
interface QueryInput {
  query: string;          // 自然语言查询文本（必填）
  doc_ids?: string[];     // 限定文档 ID 列表；空数组或缺省表示全库检索
  top_k?: number;         // 返回片段数量；默认 5，最大 20
  mode?: "semantic" | "keyword" | "hybrid";  // 检索模式；默认 "hybrid"
  expand_context?: boolean;  // 是否返回目标片段的前后相邻片段；默认 false
}
```

**约束**:
- `query` 长度超过 2000 字符时，系统自动截断至 2000 字符并在响应中标注
- `top_k` 超出 20 时，系统强制截断至 20 并返回 warning
- `doc_ids` 包含不存在的 ID 时，忽略无效 ID，仅对有效 ID 检索

---

## 输出 Schema

```typescript
interface QueryOutput {
  results: ChunkResult[];
  total_found: number;     // 候选池大小（RRF 融合前）
  strategy_used: "semantic" | "keyword" | "hybrid";
  query_truncated: boolean;
  warnings: string[];
  latency_ms: number;
}

interface ChunkResult {
  chunk_id: string;
  document_id: string;
  document_title: string;
  content: string;          // 片段文本内容
  score: number;            // 相关性分数 0.0–1.0（RRF + rerank 归一化后）
  position: ChunkPosition;
  context?: ContextWindow;  // 仅当 expand_context=true 时返回
}

interface ChunkPosition {
  page_no: number | null;
  heading_breadcrumb: string;    // 例: "第2章 安装指南 > 2.3 环境配置 > 表2-1"
  element_type: "PARAGRAPH" | "TABLE" | "TABLE_PART" | "SECTION_HEADER" | "LIST_ITEM";
  element_index_on_page: number | null;
  chunk_index: number;           // 在文档中的连续序号（用于 read 技能导航）
}

interface ContextWindow {
  prev_chunk?: ChunkResult;   // 前一个片段（不含 score）
  next_chunk?: ChunkResult;   // 后一个片段（不含 score）
}
```

---

## 错误响应

| HTTP 码 | Error Code | 触发条件 |
|---------|-----------|----------|
| 400 | `QUERY_EMPTY` | query 为空字符串 |
| 400 | `INVALID_MODE` | mode 不在允许值列表中 |
| 404 | `NO_DOCS_FOUND` | 所有 doc_ids 均不存在 |
| 503 | `INDEX_NOT_READY` | 指定文档仍在索引中（status ≠ indexed） |
| 200 | (warning) | 文档库为空，results 为空数组，warnings 包含提示 |

---

## 示例

**请求**:
```json
{
  "query": "如何配置数据库连接池？",
  "doc_ids": ["42", "78"],
  "top_k": 3,
  "mode": "hybrid"
}
```

**响应**:
```json
{
  "results": [
    {
      "chunk_id": "1024",
      "document_id": "42",
      "document_title": "系统部署手册 v2.1",
      "content": "## 数据库连接池配置\n\n| 参数 | 默认值 | 说明 |\n|------|--------|------|\n| pool_size | 10 | 最大连接数 |...",
      "score": 0.92,
      "position": {
        "page_no": 15,
        "heading_breadcrumb": "第3章 部署配置 > 3.2 数据库 > 连接池参数表",
        "element_type": "TABLE",
        "element_index_on_page": 1,
        "chunk_index": 87
      }
    }
  ],
  "total_found": 40,
  "strategy_used": "hybrid",
  "query_truncated": false,
  "warnings": [],
  "latency_ms": 312
}
```
