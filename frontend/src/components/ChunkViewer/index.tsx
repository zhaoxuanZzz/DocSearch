import {
  BookOutlined,
  DownOutlined,
  FileTextOutlined,
  UpOutlined,
} from '@ant-design/icons'
import { Card, Progress, Space, Tag, Tooltip, Typography } from 'antd'
import { useState } from 'react'
import type { ChunkResult } from '../../services/skillsApi'

const { Text, Paragraph } = Typography

// ── Strategy badge ─────────────────────────────────────────────────────────

const STRATEGY_LABELS: Record<string, { color: string; text: string }> = {
  hybrid: { color: '#2563EB', text: '混合检索' },
  semantic: { color: '#7C3AED', text: '语义检索' },
  keyword: { color: '#0891B2', text: '关键词' },
  cache: { color: '#16A34A', text: '缓存命中' },
  reranked: { color: '#F97316', text: '精排' },
}

export function StrategyBadge({ strategy }: { strategy: string }) {
  const cfg = STRATEGY_LABELS[strategy] ?? { color: '#64748B', text: strategy }
  return (
    <Tag
      style={{
        color: cfg.color,
        borderColor: cfg.color + '40',
        background: cfg.color + '10',
        fontWeight: 600,
        borderRadius: 6,
        fontSize: 11,
        lineHeight: '18px',
      }}
    >
      {cfg.text}
    </Tag>
  )
}

// ── Element type tag ───────────────────────────────────────────────────────

const ELEMENT_COLORS: Record<string, string> = {
  TABLE: '#D97706',
  TABLE_PART: '#D97706',
  SECTION_HEADER: '#7C3AED',
  TEXT: '#64748B',
  LIST_ITEM: '#0891B2',
}

function ElementTag({ type }: { type: string }) {
  const color = ELEMENT_COLORS[type] ?? '#64748B'
  return (
    <Tag
      style={{
        color,
        borderColor: color + '40',
        background: color + '12',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 500,
        margin: 0,
        lineHeight: '18px',
      }}
    >
      {type}
    </Tag>
  )
}

// ── Breadcrumb chain ───────────────────────────────────────────────────────

function BreadcrumbChain({ path }: { path: string }) {
  if (!path) return null
  const parts = path.split(' > ')
  return (
    <Space size={2} wrap>
      {parts.map((part, i) => (
        <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {i > 0 && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              {'>'}
            </Text>
          )}
          <Tag
            style={{
              margin: 0,
              borderRadius: 4,
              fontSize: 11,
              lineHeight: '18px',
              background: '#F1F5F9',
              borderColor: '#E2E8F0',
              color: '#475569',
              maxWidth: 180,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={part}
          >
            {part}
          </Tag>
        </span>
      ))}
    </Space>
  )
}

// ── Chunk card ─────────────────────────────────────────────────────────────

const COLLAPSE_THRESHOLD = 300 // characters

interface ChunkViewerProps {
  chunk: ChunkResult
  rank?: number
  highlight?: string
}

export default function ChunkViewer({ chunk, rank, highlight }: ChunkViewerProps) {
  const [expanded, setExpanded] = useState(false)
  const isLong = chunk.content.length > COLLAPSE_THRESHOLD
  const displayContent =
    isLong && !expanded
      ? chunk.content.slice(0, COLLAPSE_THRESHOLD) + '…'
      : chunk.content

  // Score bar
  const scorePercent = Math.round(chunk.score * 100)
  const scoreColor =
    chunk.score >= 0.7 ? '#16A34A' : chunk.score >= 0.4 ? '#F97316' : '#94A3B8'

  return (
    <Card
      style={{
        borderRadius: 10,
        border: '1px solid #E2E8F0',
        marginBottom: 12,
        transition: 'box-shadow 0.2s ease-out',
      }}
      hoverable
      bodyStyle={{ padding: '14px 18px' }}
    >
      {/* ── Header row ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: 8,
          gap: 8,
        }}
      >
        {/* Left: rank + document title */}
        <Space size={8} align="center">
          {rank != null && (
            <div
              style={{
                width: 24,
                height: 24,
                borderRadius: '50%',
                background: rank <= 3 ? '#2563EB' : '#E2E8F0',
                color: rank <= 3 ? '#fff' : '#64748B',
                fontSize: 11,
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              {rank}
            </div>
          )}
          <div>
            <Space size={6}>
              <FileTextOutlined style={{ color: '#64748B', fontSize: 12 }} />
              <Text strong style={{ fontSize: 13, color: '#0F172A' }}>
                {chunk.document_title}
              </Text>
            </Space>
          </div>
        </Space>

        {/* Right: score */}
        <Tooltip title={`相关度得分: ${chunk.score.toFixed(4)}`}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
            <Progress
              percent={scorePercent}
              size="small"
              showInfo={false}
              strokeColor={scoreColor}
              trailColor="#F1F5F9"
              style={{ width: 60, margin: 0 }}
            />
            <Text
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: scoreColor,
                fontVariantNumeric: 'tabular-nums',
                minWidth: 32,
              }}
            >
              {chunk.score.toFixed(3)}
            </Text>
          </div>
        </Tooltip>
      </div>

      {/* ── Position metadata row ── */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 6,
          marginBottom: 10,
          alignItems: 'center',
        }}
      >
        <ElementTag type={chunk.position.element_type} />
        {chunk.position.page_no != null && (
          <Tag
            style={{
              margin: 0,
              fontSize: 11,
              borderRadius: 4,
              lineHeight: '18px',
              background: '#EFF6FF',
              borderColor: '#BFDBFE',
              color: '#2563EB',
            }}
          >
            P{chunk.position.page_no}
          </Tag>
        )}
        <Text type="secondary" style={{ fontSize: 11 }}>
          Chunk #{chunk.position.chunk_index}
        </Text>
      </div>

      {/* ── Breadcrumb ── */}
      {chunk.position.heading_breadcrumb && (
        <div style={{ marginBottom: 10 }}>
          <Space size={4} align="center">
            <BookOutlined style={{ color: '#94A3B8', fontSize: 11 }} />
            <BreadcrumbChain path={chunk.position.heading_breadcrumb} />
          </Space>
        </div>
      )}

      {/* ── Content ── */}
      <div
        style={{
          background: '#F8FAFC',
          borderRadius: 6,
          padding: '10px 12px',
          borderLeft: '3px solid #CBD5E1',
        }}
      >
        <Paragraph
          style={{
            margin: 0,
            fontSize: 13,
            lineHeight: 1.65,
            color: '#334155',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {displayContent}
        </Paragraph>
      </div>

      {/* ── Expand / collapse ── */}
      {isLong && (
        <div style={{ marginTop: 8, textAlign: 'center' }}>
          <Text
            style={{
              fontSize: 12,
              color: '#2563EB',
              cursor: 'pointer',
              userSelect: 'none',
            }}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? (
              <>
                <UpOutlined style={{ marginRight: 4 }} />
                收起
              </>
            ) : (
              <>
                <DownOutlined style={{ marginRight: 4 }} />
                展开全文（{chunk.content.length} 字符）
              </>
            )}
          </Text>
        </div>
      )}
    </Card>
  )
}
