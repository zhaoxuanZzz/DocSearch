import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 60_000,
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data?.detail
    const message =
      typeof detail === 'object' ? detail.message : detail ?? err.message
    return Promise.reject(new Error(message))
  },
)

// ── Types ──────────────────────────────────────────────────────────────────

export interface ChunkPosition {
  page_no: number | null
  heading_breadcrumb: string
  element_type: string
  element_index_on_page: number | null
  chunk_index: number
}

export interface ChunkResult {
  chunk_id: string
  document_id: string
  document_title: string
  content: string
  score: number
  position: ChunkPosition
  context?: {
    prev_chunk?: ChunkResult | null
    next_chunk?: ChunkResult | null
  }
}

export interface QueryOutput {
  results: ChunkResult[]
  total_found: number
  strategy_used: string
  query_truncated: boolean
  warnings: string[]
  latency_ms: number
}

export interface ReadOutput {
  doc_id: string
  doc_title: string
  content: string
  chunks_returned: number
  position_start: ChunkPosition
  position_end: ChunkPosition
  next_cursor: string | null
  is_end_of_document: boolean
  mode_used: string
}

export interface RoutingResponse {
  recommended_skill: 'query' | 'read' | 'grep'
  fallback_skill: 'query' | 'read' | 'grep' | null
  confidence: number
  reason: string
  doc_stats: {
    total_docs: number
    total_chunks: number
    total_size_bytes: number
    indexed_docs: number
    unindexed_docs: number
  }
  thresholds_applied: {
    small_doc_threshold: number
    small_size_threshold_mb: number
    low_confidence_score_threshold: number
  }
  low_confidence_note?: string
}

// ── Query skill ────────────────────────────────────────────────────────────

export async function queryDocuments(params: {
  query: string
  doc_ids?: string[]
  top_k?: number
  mode?: 'semantic' | 'keyword' | 'hybrid'
  expand_context?: boolean
}): Promise<QueryOutput> {
  const res = await http.post<QueryOutput>('/skills/query', {
    ...params,
    top_k: params.top_k ?? 5,
    mode: params.mode ?? 'hybrid',
    expand_context: params.expand_context ?? false,
  })
  return res.data
}

// ── Read skill ────────────────────────────────────────────────────────────

export async function readDocument(params: {
  doc_id: string
  cursor?: string
  start_breadcrumb?: string
  start_page?: number
  mode?: 'token' | 'heading'
  max_tokens?: number
}): Promise<ReadOutput> {
  const res = await http.post<ReadOutput>('/skills/read', params)
  return res.data
}

// ── Routing advisor ───────────────────────────────────────────────────────

export async function getRoutingSuggestion(params: {
  doc_ids?: string[]
  query_intent: 'semantic' | 'exact' | 'pattern' | 'sequential'
  query_sample?: string
}): Promise<RoutingResponse> {
  const res = await http.post<RoutingResponse>('/routing/suggest', params)
  return res.data
}
