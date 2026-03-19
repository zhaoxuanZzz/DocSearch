# Contract: grep 技能

**Skill**: `grep_documents`  
**FR Reference**: FR-021, FR-021a  
**Version**: 1.0

---

## 功能描述

在指定文档集的完整文本中执行正则表达式或关键词模式匹配，返回所有匹配位置列表（按文档分组），每个匹配携带精准位置信息及前后各 1 行上下文。

---

## 输入 Schema

```typescript
interface GrepInput {
  pattern: string;          // 正则表达式或关键词（必填）
  doc_ids?: string[];       // 目标文档 ID 列表；空数组或缺省表示全库
  is_regex?: boolean;       // pattern 是否为正则表达式；默认 false（关键词模式）
  case_sensitive?: boolean; // 是否区分大小写；默认 false
  context_lines?: number;   // 返回匹配行前后的上下文行数；默认 1，最大 3
  max_matches_per_doc?: number;  // 每个文档最多返回的匹配数；默认 50
}
```

**约束**:
- `doc_ids` 不填时默认检索全库，但总目标文档数不得超过系统配置上限（默认 20）
- 若目标文档总数超过上限，返回 `DOC_LIMIT_EXCEEDED` 错误，提示缩小范围或改用 `query`
- `pattern` 为正则时，若语法错误则返回 `INVALID_PATTERN` 错误
- `max_matches_per_doc` 达到上限后，在该文档结果中标注 `truncated: true`

---

## 输出 Schema

```typescript
interface GrepOutput {
  results: GrepDocResult[];
  total_docs_searched: number;
  total_matches: number;
  pattern_used: string;
  warnings: string[];
}

interface GrepDocResult {
  document_id: string;
  document_title: string;
  match_count: number;
  truncated: boolean;        // 是否因 max_matches_per_doc 截断
  matches: GrepMatch[];
}

interface GrepMatch {
  match_text: string;        // 精确匹配的文本内容
  line_content: string;      // 匹配所在的完整行内容
  context_before: string[];  // 匹配行之前的上下文行（最多 context_lines 条）
  context_after: string[];   // 匹配行之后的上下文行（最多 context_lines 条）
  position: ChunkPosition;   // 所在片段的精准位置（含页码、标题路径）
  chunk_id: string;
}
```

（`ChunkPosition` 定义同 query-skill.md）

---

## 错误响应

| HTTP 码 | Error Code | 触发条件 |
|---------|-----------|----------|
| 400 | `PATTERN_EMPTY` | pattern 为空字符串 |
| 400 | `INVALID_PATTERN` | is_regex=true 且正则语法无效 |
| 400 | `DOC_LIMIT_EXCEEDED` | 目标文档总数超过系统配置上限。响应体中包含 `max_allowed` 和 `requested` 字段，以及建议改用 `query` 的提示 |
| 404 | `NO_DOCS_FOUND` | 所有指定 doc_ids 均不存在 |
| 503 | `DOCS_NOT_INDEXED` | 部分文档 status ≠ indexed（响应中列出未就绪文档） |

**`DOC_LIMIT_EXCEEDED` 响应体**:
```json
{
  "error": "DOC_LIMIT_EXCEEDED",
  "message": "目标文档数量 (35) 超过 grep 技能上限 (20)。建议：(1) 缩小 doc_ids 列表；(2) 使用 query 技能进行大范围语义检索。",
  "max_allowed": 20,
  "requested": 35
}
```

---

## 示例

**请求（正则模式，在指定文档中找所有 API KEY 配置项）**:
```json
{
  "pattern": "API_KEY\\s*=\\s*[^\\s]+",
  "doc_ids": ["42", "78", "95"],
  "is_regex": true,
  "case_sensitive": true,
  "context_lines": 2
}
```

**响应**:
```json
{
  "results": [
    {
      "document_id": "42",
      "document_title": "系统部署手册 v2.1",
      "match_count": 3,
      "truncated": false,
      "matches": [
        {
          "match_text": "API_KEY = sk-abc123",
          "line_content": "API_KEY = sk-abc123  # 生产环境密钥",
          "context_before": ["# 环境变量配置", ""],
          "context_after": ["SECRET_KEY = xyz789", "DATABASE_URL = ..."],
          "position": {
            "page_no": 8,
            "heading_breadcrumb": "第2章 环境配置 > 2.1 环境变量",
            "element_type": "PARAGRAPH",
            "element_index_on_page": 2,
            "chunk_index": 41
          },
          "chunk_id": "890"
        }
      ]
    }
  ],
  "total_docs_searched": 3,
  "total_matches": 3,
  "pattern_used": "API_KEY\\s*=\\s*[^\\s]+",
  "warnings": []
}
```
