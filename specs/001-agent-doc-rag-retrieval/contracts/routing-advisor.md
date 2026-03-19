# Contract: 路由建议接口

**Endpoint**: `POST /api/v1/routing/suggest`  
**FR Reference**: FR-022, FR-023, FR-024, FR-025  
**Version**: 1.0

---

## 功能描述

接受 Agent 提供的目标文档集描述和查询意图，返回推荐的检索策略（`query`/`read`/`grep`）及客观依据。系统不强制执行路由，Agent 可自主决定是否采纳。

---

## 输入 Schema

```typescript
interface RoutingRequest {
  doc_ids?: string[];        // 目标文档 ID 列表；空/缺省表示全库
  query_intent: "semantic" | "exact" | "pattern" | "sequential";
  // semantic  = 概念性/语义查询（适合 query）
  // exact     = 精确词汇/术语查找（适合 grep/query）
  // pattern   = 正则或结构化模式匹配（适合 grep）
  // sequential = 需要顺序阅读/理解章节（适合 read）
  query_sample?: string;     // 查询示例文本（可选，用于更精准的建议）
}
```

---

## 输出 Schema

```typescript
interface RoutingResponse {
  recommended_skill: "query" | "read" | "grep";
  fallback_skill: "query" | "read" | "grep" | null;
  confidence: number;        // 0.0–1.0，推荐置信度
  reason: string;            // 人类可读的推荐理由
  doc_stats: DocStats;       // 文档集客观指标
  thresholds_applied: ThresholdInfo;  // 路由决策中使用的阈值
  low_confidence_note?: string;  // 仅当 confidence < 0.6 时，说明边界情况
}

interface DocStats {
  total_docs: number;
  total_chunks: number;
  total_size_bytes: number;
  indexed_docs: number;      // status=indexed 的文档数
  unindexed_docs: number;    // 尚未完成索引的文档数
}

interface ThresholdInfo {
  small_doc_threshold: number;   // 文档数量阈值（当前配置值）
  small_size_threshold_mb: number;  // 文档体积阈值（当前配置值，单位 MB）
  low_confidence_score_threshold: number;  // query 低置信度阈值
}
```

---

## 路由决策逻辑（系统内部，供理解参考）

```
输入: doc_count, total_size, query_intent

IF doc_count <= small_doc_threshold AND total_size <= small_size_threshold:
    IF query_intent == "pattern":
        recommend "grep"；reason = "小文档集 + 模式查询，grep 精准定位"
    ELIF query_intent == "sequential":
        recommend "read"；reason = "小文档集 + 顺序阅读需求，read 覆盖完整内容"
    ELSE:
        recommend "grep" if exact, else "read"；reason = "文档集较小，直接阅读比向量召回更精准"
ELSE:
    recommend "query"；reason = "文档集较大，RAG 召回性价比最优"

IF recommended == "query" AND query_intent == "sequential":
    fallback = "read"；low_confidence_note = "顺序阅读场景 query 可能不完整，建议按需补充 read"
```

---

## 错误响应

| HTTP 码 | Error Code | 触发条件 |
|---------|-----------|----------|
| 400 | `INVALID_INTENT` | query_intent 不在允许值列表中 |
| 404 | `NO_DOCS_FOUND` | 指定 doc_ids 均不存在 |

---

## 示例

**请求（5 份文档，精确术语查找）**:
```json
{
  "doc_ids": ["10", "11", "12", "13", "14"],
  "query_intent": "exact",
  "query_sample": "POOL_MAX_SIZE 配置项在哪里"
}
```

**响应**:
```json
{
  "recommended_skill": "grep",
  "fallback_skill": "query",
  "confidence": 0.88,
  "reason": "目标文档集仅 5 份（共 1.2MB），低于小文档阈值（5份/1MB）。查询意图为精确术语查找，grep 可直接定位所有出现位置，优于向量召回。",
  "doc_stats": {
    "total_docs": 5,
    "total_chunks": 312,
    "total_size_bytes": 1258291,
    "indexed_docs": 5,
    "unindexed_docs": 0
  },
  "thresholds_applied": {
    "small_doc_threshold": 5,
    "small_size_threshold_mb": 1.0,
    "low_confidence_score_threshold": 0.5
  }
}
```

**请求（100 份文档，语义查询）**:
```json
{
  "doc_ids": [],
  "query_intent": "semantic",
  "query_sample": "如何处理网络超时导致的服务降级"
}
```

**响应**:
```json
{
  "recommended_skill": "query",
  "fallback_skill": null,
  "confidence": 0.95,
  "reason": "全库共 247 份文档（总计 892MB），远超小文档阈值。语义查询使用 RAG 混合召回可快速缩小范围，直接阅读代价过高。",
  "doc_stats": {
    "total_docs": 247,
    "total_chunks": 31840,
    "total_size_bytes": 935329792,
    "indexed_docs": 245,
    "unindexed_docs": 2
  },
  "thresholds_applied": {
    "small_doc_threshold": 5,
    "small_size_threshold_mb": 1.0,
    "low_confidence_score_threshold": 0.5
  }
}
```
