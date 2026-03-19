# Contract: read 技能

**Skill**: `read_document`  
**FR Reference**: FR-011, FR-020  
**Version**: 1.0

---

## 功能描述

按文档结构顺序阅读指定文档，支持从指定页码或标题路径位置开始，通过翻页 cursor 实现分段连续阅读。支持两种翻页模式：固定 Token 数模式和标题块（Heading Block）模式。

---

## 输入 Schema

```typescript
interface ReadInput {
  doc_id: string;           // 文档 ID（必填）

  // 起始位置（二选一，均不填则从头开始）
  start_page?: number;             // 从指定页码开始（1-based）
  start_breadcrumb?: string;       // 从指定标题路径开始（前缀匹配）

  // 翻页 cursor（继续阅读时填写）
  cursor?: string;                 // 上次返回的 next_cursor，不填则为首次阅读

  // 阅读模式（二选一）
  mode?: "token" | "heading";      // 默认 "heading"
  max_tokens?: number;             // mode="token" 时有效；默认 2000，最大 4000
}
```

**约束**:
- `start_page` 和 `start_breadcrumb` 同时填写时，优先使用 `start_breadcrumb`
- `cursor` 与 `start_page`/`start_breadcrumb` 同时填写时，优先使用 `cursor`
- `start_breadcrumb` 为前缀匹配，例如 `"第2章"` 匹配任何以 "第2章" 开头的标题路径

---

## 输出 Schema

```typescript
interface ReadOutput {
  doc_id: string;
  doc_title: string;
  content: string;           // 本次返回的完整内容（Markdown 格式）
  chunks_returned: number;   // 本次包含的 Chunk 数量
  position_start: ChunkPosition;  // 本次内容起始位置
  position_end: ChunkPosition;    // 本次内容结束位置
  next_cursor: string | null;     // 继续阅读的游标；null 表示已到文档末尾
  is_end_of_document: boolean;
  mode_used: "token" | "heading";
}
```

（`ChunkPosition` 定义同 query-skill.md）

---

## 翻页语义说明

### token 模式
从起始 Chunk 开始，累积 Chunk 内容直至达到 `max_tokens` 上限（或文档末尾），返回结果。`next_cursor` 指向下一个未返回的 Chunk。

### heading 模式
从起始 Chunk 所在的最顶层标题块开始，返回该标题块（章节）下的所有 Chunk 内容，包括其下所有子标题的内容。`next_cursor` 指向下一个同级标题块的起始位置。

---

## 错误响应

| HTTP 码 | Error Code | 触发条件 |
|---------|-----------|----------|
| 400 | `INVALID_CURSOR` | cursor 格式无效或已过期 |
| 404 | `DOC_NOT_FOUND` | doc_id 不存在 |
| 404 | `POSITION_NOT_FOUND` | start_page 或 start_breadcrumb 在文档中无匹配 |
| 503 | `DOC_NOT_INDEXED` | 文档 status ≠ indexed |

---

## 示例

**请求（首次，从特定章节开始）**:
```json
{
  "doc_id": "42",
  "start_breadcrumb": "第3章 部署配置",
  "mode": "heading"
}
```

**响应**:
```json
{
  "doc_id": "42",
  "doc_title": "系统部署手册 v2.1",
  "content": "## 第3章 部署配置\n\n本章介绍系统部署的详细配置...\n\n### 3.1 环境要求\n...",
  "chunks_returned": 8,
  "position_start": {
    "page_no": 12,
    "heading_breadcrumb": "第3章 部署配置",
    "element_type": "SECTION_HEADER",
    "element_index_on_page": 0,
    "chunk_index": 60
  },
  "position_end": {
    "page_no": 18,
    "heading_breadcrumb": "第3章 部署配置 > 3.3 网络配置",
    "element_type": "PARAGRAPH",
    "element_index_on_page": 3,
    "chunk_index": 92
  },
  "next_cursor": "eyJjaHVua19pbmRleCI6IDkzfQ==",
  "is_end_of_document": false,
  "mode_used": "heading"
}
```

**继续阅读请求**:
```json
{
  "doc_id": "42",
  "cursor": "eyJjaHVua19pbmRleCI6IDkzfQ=="
}
```
