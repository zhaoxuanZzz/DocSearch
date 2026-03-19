import {
  BulbOutlined,
  FilterOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Collapse,
  Empty,
  Segmented,
  Select,
  Skeleton,
  Slider,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import TextArea from 'antd/es/input/TextArea'
import { useCallback, useEffect, useState } from 'react'
import ChunkViewer, { StrategyBadge } from '../../components/ChunkViewer'
import { listDocuments } from '../../services/documentApi'
import type { DocumentResponse } from '../../services/documentApi'
import { queryDocuments } from '../../services/skillsApi'
import type { QueryOutput } from '../../services/skillsApi'

const { Text, Title, Paragraph } = Typography

// ── Mode labels ────────────────────────────────────────────────────────────

const MODE_OPTIONS = [
  { label: '语义', value: 'hybrid' },
  { label: '关键词', value: 'keyword' },
  { label: '纯向量', value: 'semantic' },
] as const

type SearchMode = 'hybrid' | 'keyword' | 'semantic'

// ── Latency badge ──────────────────────────────────────────────────────────

function LatencyBadge({ ms }: { ms: number }) {
  const color = ms < 500 ? '#16A34A' : ms < 2000 ? '#D97706' : '#DC2626'
  return (
    <Tag
      style={{
        color,
        borderColor: color + '40',
        background: color + '10',
        fontWeight: 600,
        borderRadius: 6,
        fontSize: 12,
        lineHeight: '22px',
      }}
    >
      <ThunderboltOutlined style={{ marginRight: 3 }} />
      {ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms}ms`}
    </Tag>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export default function SearchPanel() {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<SearchMode>('hybrid')
  const [topK, setTopK] = useState(5)
  const [expandCtx, setExpandCtx] = useState(false)
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const [allDocs, setAllDocs] = useState<DocumentResponse[]>([])
  const [docsLoading, setDocsLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [result, setResult] = useState<QueryOutput | null>(null)
  const [error, setError] = useState<string | null>(null)

  // ── Load indexed documents ─────────────────────────────────────────────
  useEffect(() => {
    listDocuments(1, 100, 'indexed')
      .then((docs) => setAllDocs(docs))
      .catch(() => {})
      .finally(() => setDocsLoading(false))
  }, [])

  // ── Search ─────────────────────────────────────────────────────────────
  const handleSearch = useCallback(async () => {
    const q = query.trim()
    if (!q) return
    setSearching(true)
    setResult(null)
    setError(null)
    try {
      const out = await queryDocuments({
        query: q,
        doc_ids: selectedDocIds.length > 0 ? selectedDocIds : undefined,
        top_k: topK,
        mode,
        expand_context: expandCtx,
      })
      setResult(out)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSearching(false)
    }
  }, [query, mode, topK, expandCtx, selectedDocIds])

  const docOptions = allDocs
    .filter((d) => d.status === 'indexed')
    .map((d) => ({
      label: d.title,
      value: String(d.id),
    }))

  return (
    <div>
      {/* ── Page header ── */}
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0, color: '#0F172A' }}>
          检索测试
        </Title>
        <Text type="secondary" style={{ fontSize: 13 }}>
          向量 / 关键词 / 混合检索，支持上下文扩展
        </Text>
      </div>

      {/* ── Search card ── */}
      <Card
        style={{ borderRadius: 12, border: '1px solid #E2E8F0', marginBottom: 20 }}
      >
        {/* Query input */}
        <TextArea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSearch()
            }
          }}
          placeholder="输入检索问题，按 Enter 搜索（Shift+Enter 换行）…"
          autoSize={{ minRows: 2, maxRows: 6 }}
          style={{
            fontSize: 15,
            borderRadius: 8,
            resize: 'none',
            lineHeight: 1.6,
          }}
          maxLength={2000}
          showCount
        />

        {/* Controls row */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 16,
            marginTop: 14,
            alignItems: 'flex-end',
          }}
        >
          {/* Mode selector */}
          <div>
            <Text
              type="secondary"
              style={{ fontSize: 12, display: 'block', marginBottom: 6 }}
            >
              检索模式
            </Text>
            <Segmented
              value={mode}
              onChange={(v) => setMode(v as SearchMode)}
              options={MODE_OPTIONS}
              style={{ fontWeight: 500 }}
            />
          </div>

          {/* TopK slider */}
          <div style={{ flex: '0 0 200px' }}>
            <Text
              type="secondary"
              style={{ fontSize: 12, display: 'block', marginBottom: 6 }}
            >
              返回数量：<Text strong>{topK}</Text>
            </Text>
            <Slider
              min={1}
              max={20}
              value={topK}
              onChange={setTopK}
              marks={{ 1: '1', 5: '5', 10: '10', 20: '20' }}
              style={{ margin: '0 6px' }}
            />
          </div>

          {/* Expand context toggle */}
          <div style={{ alignSelf: 'flex-end', paddingBottom: 4 }}>
            <Checkbox
              checked={expandCtx}
              onChange={(e) => setExpandCtx(e.target.checked)}
            >
              <Text style={{ fontSize: 13 }}>扩展上下文</Text>
            </Checkbox>
          </div>

          {/* Submit button */}
          <div style={{ marginLeft: 'auto', alignSelf: 'flex-end' }}>
            <Button
              type="primary"
              size="large"
              icon={<SearchOutlined />}
              loading={searching}
              onClick={handleSearch}
              disabled={!query.trim()}
              style={{
                borderRadius: 8,
                fontWeight: 600,
                minWidth: 100,
                height: 42,
              }}
            >
              检索
            </Button>
          </div>
        </div>

        {/* Doc selector (advanced) */}
        <Collapse
          ghost
          style={{ marginTop: 8 }}
          items={[
            {
              key: '1',
              label: (
                <Text style={{ fontSize: 13, color: '#64748B' }}>
                  <FilterOutlined style={{ marginRight: 6 }} />
                  限定文档范围
                  {selectedDocIds.length > 0 && (
                    <Tag
                      color="blue"
                      style={{ marginLeft: 8, borderRadius: 10, fontSize: 11 }}
                    >
                      {selectedDocIds.length}
                    </Tag>
                  )}
                </Text>
              ),
              children: (
                <Select
                  mode="multiple"
                  placeholder={
                    docsLoading ? '加载文档列表…' : '选择文档（留空=全部检索）'
                  }
                  value={selectedDocIds}
                  onChange={setSelectedDocIds}
                  options={docOptions}
                  loading={docsLoading}
                  style={{ width: '100%' }}
                  showSearch
                  filterOption={(input, option) =>
                    (option?.label as string)
                      ?.toLowerCase()
                      .includes(input.toLowerCase()) ?? false
                  }
                  allowClear
                  maxTagCount="responsive"
                />
              ),
            },
          ]}
        />
      </Card>

      {/* ── Error ── */}
      {error && (
        <Alert
          type="error"
          message={error}
          closable
          onClose={() => setError(null)}
          style={{ marginBottom: 16, borderRadius: 8 }}
        />
      )}

      {/* ── Loading skeleton ── */}
      {searching && (
        <Card style={{ borderRadius: 12, border: '1px solid #E2E8F0' }}>
          {[1, 2, 3].map((i) => (
            <div key={i} style={{ marginBottom: i < 3 ? 20 : 0 }}>
              <Skeleton active avatar={{ shape: 'circle', size: 'small' }} paragraph={{ rows: 3 }} />
            </div>
          ))}
        </Card>
      )}

      {/* ── Results ── */}
      {result && !searching && (
        <div>
          {/* Results meta */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              marginBottom: 16,
              flexWrap: 'wrap',
            }}
          >
            <Text strong style={{ fontSize: 14 }}>
              找到 {result.total_found} 个相关片段
            </Text>
            <StrategyBadge strategy={result.strategy_used} />
            <LatencyBadge ms={result.latency_ms} />

            {result.query_truncated && (
              <Tooltip title="查询文本超出最大长度，已自动截断">
                <Tag color="orange" style={{ borderRadius: 6 }}>
                  查询已截断
                </Tag>
              </Tooltip>
            )}
          </div>

          {/* Warnings */}
          {result.warnings.length > 0 && (
            <Alert
              type="warning"
              icon={<BulbOutlined />}
              showIcon
              message={
                <Space direction="vertical" size={2}>
                  {result.warnings.map((w, i) => (
                    <Text key={i} style={{ fontSize: 12 }}>
                      {w}
                    </Text>
                  ))}
                </Space>
              }
              style={{ marginBottom: 16, borderRadius: 8 }}
            />
          )}

          {/* Chunk cards */}
          {result.results.length === 0 ? (
            <Empty
              description={<Text type="secondary">未检索到相关内容，尝试换个问法</Text>}
              style={{ padding: '40px 0' }}
            />
          ) : (
            result.results.map((chunk, idx) => (
              <ChunkViewer
                key={chunk.chunk_id}
                chunk={chunk}
                rank={idx + 1}
                highlight={query}
              />
            ))
          )}
        </div>
      )}

      {/* ── Initial empty state ── */}
      {!result && !searching && !error && (
        <Card
          style={{
            borderRadius: 12,
            border: '1px dashed #CBD5E1',
            textAlign: 'center',
            padding: '40px 0',
          }}
        >
          <SearchOutlined
            style={{ fontSize: 40, color: '#CBD5E1', display: 'block', marginBottom: 12 }}
          />
          <Text type="secondary">输入问题开始检索</Text>
        </Card>
      )}
    </div>
  )
}
