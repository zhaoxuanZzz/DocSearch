import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
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

export interface DocumentResponse {
  id: number
  title: string
  file_name: string
  format: string
  file_size: number | null
  minio_key: string
  markdown_key: string | null
  chunk_count: number
  status: 'pending' | 'processing' | 'indexed' | 'failed'
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface DocumentStatusResponse {
  id: number
  status: string
  chunk_count: number
  error_message: string | null
  progress: number | null
}

export interface DocumentStats {
  total_documents: number
  total_chunks: number
  indexed_documents: number
  processing_documents: number
  pending_documents: number
  failed_documents: number
}

// ── API calls ──────────────────────────────────────────────────────────────

export async function uploadDocument(file: File): Promise<DocumentResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await http.post<DocumentResponse>('/documents/upload', form)
  return res.data
}

export async function listDocuments(
  page = 1,
  pageSize = 20,
  status?: string,
): Promise<DocumentResponse[]> {
  const res = await http.get<DocumentResponse[]>('/documents/', {
    params: { page, page_size: pageSize, ...(status ? { status } : {}) },
  })
  return res.data
}

export async function getDocumentStatus(
  id: number,
): Promise<DocumentStatusResponse> {
  const res = await http.get<DocumentStatusResponse>(
    `/documents/${id}/status`,
  )
  return res.data
}

export async function getDocumentStats(): Promise<DocumentStats> {
  const res = await http.get<DocumentStats>('/documents/stats')
  return res.data
}

export async function updateDocument(
  id: number,
  file: File,
): Promise<DocumentStatusResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await http.put<DocumentStatusResponse>(`/documents/${id}`, form)
  return res.data
}

export async function deleteDocument(id: number): Promise<void> {
  await http.delete(`/documents/${id}`)
}
