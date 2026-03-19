import {
  CheckCircleFilled,
  ClockCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  ExclamationCircleFilled,
  FileOutlined,
  LoadingOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import {
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Modal,
  Row,
  Skeleton,
  Space,
  Statistic,
  Table,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { UploadProps } from 'antd/es/upload'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteDocument,
  getDocumentStats,
  getDocumentStatus,
  listDocuments,
  uploadDocument,
} from '../../services/documentApi'
import type { DocumentResponse, DocumentStats } from '../../services/documentApi'

const { Title, Text, Paragraph } = Typography
const { Dragger } = Upload

// ── Status helpers ─────────────────────────────────────────────────────────

type DocStatus = 'pending' | 'processing' | 'indexed' | 'failed'

const STATUS_CONFIG: Record<
  DocStatus,
  { color: string; icon: React.ReactNode; label: string; badge: 'default' | 'processing' | 'success' | 'error' | 'warning' }
> = {
  pending: {
    color: '#F59E0B',
    icon: <ClockCircleOutlined />,
    label: '等待中',
    badge: 'warning',
  },
  processing: {
    color: '#2563EB',
    icon: <SyncOutlined spin />,
    label: '处理中',
    badge: 'processing',
  },
  indexed: {
    color: '#16A34A',
    icon: <CheckCircleFilled />,
    label: '已索引',
    badge: 'success',
  },
  failed: {
    color: '#DC2626',
    icon: <ExclamationCircleFilled />,
    label: '失败',
    badge: 'error',
  },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CONFIG[status as DocStatus] ?? STATUS_CONFIG.pending
  return (
    <Space size={6}>
      <Badge status={cfg.badge} />
      <Text style={{ color: cfg.color, fontSize: 13, fontWeight: 500 }}>
        {cfg.label}
      </Text>
    </Space>
  )
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

// ── Main component ─────────────────────────────────────────────────────────

export default function DocumentLibrary() {
  const [docs, setDocs] = useState<DocumentResponse[]>([])
  const [stats, setStats] = useState<DocumentStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<DocumentResponse | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Load data ──────────────────────────────────────────────────────────
  const loadData = useCallback(async () => {
    try {
      const [docList, docStats] = await Promise.all([
        listDocuments(),
        getDocumentStats(),
      ])
      setDocs(docList)
      setStats(docStats)
    } catch (err) {
      message.error('加载文档列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
  }, [loadData])

  // ── Poll pending/processing docs ───────────────────────────────────────
  useEffect(() => {
    const active = docs.filter(
      (d) => d.status === 'pending' || d.status === 'processing',
    )
    if (active.length === 0) {
      if (pollingRef.current) clearInterval(pollingRef.current)
      return
    }

    pollingRef.current = setInterval(async () => {
      const updates = await Promise.all(active.map((d) => getDocumentStatus(d.id)))
      setDocs((prev) =>
        prev.map((d) => {
          const upd = updates.find((u) => u.id === d.id)
          if (!upd) return d
          return { ...d, status: upd.status as DocStatus, chunk_count: upd.chunk_count }
        }),
      )
      // Refresh stats when something completes
      if (updates.some((u) => u.status === 'indexed' || u.status === 'failed')) {
        const s = await getDocumentStats()
        setStats(s)
      }
    }, 3000)

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [docs])

  // ── Upload ─────────────────────────────────────────────────────────────
  const handleUpload: UploadProps['customRequest'] = async ({ file, onSuccess, onError }) => {
    setUploading(true)
    try {
      const doc = await uploadDocument(file as File)
      message.success(`「${doc.title}」上传成功，正在后台处理…`)
      setDocs((prev) => [doc, ...prev])
      if (stats) {
        setStats({
          ...stats,
          total_documents: stats.total_documents + 1,
          pending_documents: stats.pending_documents + 1,
        })
      }
      onSuccess?.(doc)
    } catch (err) {
      message.error((err as Error).message || '上传失败')
      onError?.(err as Error)
    } finally {
      setUploading(false)
    }
  }

  // ── Delete ─────────────────────────────────────────────────────────────
  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleteLoading(true)
    try {
      await deleteDocument(deleteTarget.id)
      message.success(`「${deleteTarget.title}」已删除`)
      setDocs((prev) => prev.filter((d) => d.id !== deleteTarget.id))
      setDeleteTarget(null)
      const s = await getDocumentStats()
      setStats(s)
    } catch (err) {
      message.error((err as Error).message || '删除失败')
    } finally {
      setDeleteLoading(false)
    }
  }

  // ── Columns ────────────────────────────────────────────────────────────
  const columns: ColumnsType<DocumentResponse> = [
    {
      title: '文档名称',
      dataIndex: 'title',
      key: 'title',
      render: (title, record) => (
        <Space>
          <FileOutlined style={{ color: '#64748B' }} />
          <div>
            <Text strong style={{ display: 'block', fontSize: 13 }}>
              {title}
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {record.file_name} · {record.format.toUpperCase()} · {formatBytes(record.file_size)}
            </Text>
          </div>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 130,
      render: (status) => <StatusBadge status={status} />,
    },
    {
      title: 'Chunk 数',
      dataIndex: 'chunk_count',
      key: 'chunk_count',
      width: 100,
      align: 'right',
      render: (n) => (
        <Text style={{ fontVariantNumeric: 'tabular-nums' }}>{n}</Text>
      ),
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (ts) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {new Date(ts).toLocaleString('zh-CN', { hour12: false })}
        </Text>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      align: 'center',
      render: (_, record) => (
        <Tooltip title="删除文档">
          <Button
            type="text"
            danger
            icon={<DeleteOutlined />}
            size="small"
            onClick={() => setDeleteTarget(record)}
            style={{ cursor: 'pointer' }}
          />
        </Tooltip>
      ),
    },
  ]

  return (
    <div>
      {/* ── Page header ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 24,
        }}
      >
        <div>
          <Title level={4} style={{ margin: 0, color: '#0F172A' }}>
            文档库
          </Title>
          <Text type="secondary" style={{ fontSize: 13 }}>
            管理已索引的文档，支持 PDF / DOCX / TXT / MD
          </Text>
        </div>
        <Button
          icon={<ReloadOutlined />}
          onClick={loadData}
          loading={loading}
          style={{ cursor: 'pointer' }}
        >
          刷新
        </Button>
      </div>

      {/* ── Stats row ── */}
      {loading ? (
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          {[1, 2, 3, 4].map((i) => (
            <Col key={i} xs={12} md={6}>
              <Card style={{ borderRadius: 12 }}>
                <Skeleton active paragraph={false} />
              </Card>
            </Col>
          ))}
        </Row>
      ) : stats ? (
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={12} md={6}>
            <Card
              style={{
                borderRadius: 12,
                border: '1px solid #E2E8F0',
                transition: 'box-shadow 0.2s ease-out',
              }}
              hoverable
            >
              <Statistic
                title="全部文档"
                value={stats.total_documents}
                valueStyle={{ color: '#1E293B', fontWeight: 700 }}
                prefix={<DatabaseOutlined style={{ color: '#2563EB', marginRight: 4 }} />}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card
              style={{ borderRadius: 12, border: '1px solid #E2E8F0' }}
              hoverable
            >
              <Statistic
                title="已索引"
                value={stats.indexed_documents}
                valueStyle={{ color: '#16A34A', fontWeight: 700 }}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card
              style={{ borderRadius: 12, border: '1px solid #E2E8F0' }}
              hoverable
            >
              <Statistic
                title="处理中"
                value={stats.processing_documents + stats.pending_documents}
                valueStyle={{ color: '#D97706', fontWeight: 700 }}
                suffix={
                  stats.processing_documents + stats.pending_documents > 0 ? (
                    <SyncOutlined spin style={{ fontSize: 14, marginLeft: 4 }} />
                  ) : null
                }
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card
              style={{ borderRadius: 12, border: '1px solid #E2E8F0' }}
              hoverable
            >
              <Statistic
                title="总 Chunk 数"
                value={stats.total_chunks}
                valueStyle={{ color: '#1E293B', fontWeight: 700 }}
              />
            </Card>
          </Col>
        </Row>
      ) : null}

      {/* ── Upload area ── */}
      <Card
        style={{
          borderRadius: 12,
          border: '1px solid #E2E8F0',
          marginBottom: 20,
        }}
      >
        <Dragger
          name="file"
          multiple={false}
          customRequest={handleUpload}
          accept=".pdf,.docx,.doc,.txt,.md"
          showUploadList={false}
          style={{
            borderRadius: 8,
            border: '2px dashed #CBD5E1',
            background: '#F8FAFC',
            padding: '24px 0',
            transition: 'all 0.2s ease-out',
          }}
        >
          <div style={{ textAlign: 'center' }}>
            {uploading ? (
              <LoadingOutlined style={{ fontSize: 36, color: '#2563EB' }} />
            ) : (
              <CloudUploadOutlined
                style={{ fontSize: 36, color: '#64748B' }}
              />
            )}
            <Paragraph style={{ marginTop: 12, marginBottom: 4, fontWeight: 600, color: '#334155' }}>
              {uploading ? '正在上传…' : '将文件拖拽到此处，或点击上传'}
            </Paragraph>
            <Text type="secondary" style={{ fontSize: 12 }}>
              支持 PDF、DOCX、TXT、MD
            </Text>
          </div>
        </Dragger>
      </Card>

      {/* ── Document table ── */}
      <Card
        style={{ borderRadius: 12, border: '1px solid #E2E8F0' }}
        bodyStyle={{ padding: 0 }}
      >
        <Table
          rowKey="id"
          dataSource={docs}
          columns={columns}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false, hideOnSinglePage: true }}
          scroll={{ x: 700 }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  <Text type="secondary">暂无文档，请上传第一份文件</Text>
                }
              />
            ),
          }}
          rowClassName={() => 'doc-row'}
          style={{ borderRadius: 12, overflow: 'hidden' }}
        />
      </Card>

      {/* ── Delete confirm modal ── */}
      <Modal
        open={!!deleteTarget}
        title="确认删除文档"
        onOk={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{ danger: true, loading: deleteLoading }}
        width={420}
      >
        <Paragraph>
          即将删除文档「<Text strong>{deleteTarget?.title}</Text>
          」，该操作将同时删除所有关联 Chunk 及 MinIO 存储文件，<Text type="danger">
            不可恢复
          </Text>。确认继续？
        </Paragraph>
      </Modal>
    </div>
  )
}


