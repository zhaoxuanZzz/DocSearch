import {
  ApiOutlined,
  BulbOutlined,
  ExperimentOutlined,
  InfoCircleOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Radio,
  Row,
  Space,
  Statistic,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd'
import { useCallback, useEffect, useState } from 'react'
import { getRoutingSuggestion } from '../../services/skillsApi'
import type { RoutingResponse } from '../../services/skillsApi'

const { Title, Text, Paragraph } = Typography

// ── Skill label map ────────────────────────────────────────────────────────

const SKILL_LABELS: Record<string, { color: string; icon: string; label: string; desc: string }> = {
  query: {
    color: '#2563EB',
    icon: '🔍',
    label: 'query — 向量检索',
    desc: '适合语义问答、模糊匹配大型文档集',
  },
  read: {
    color: '#7C3AED',
    icon: '📖',
    label: 'read — 顺序阅读',
    desc: '适合按章节阅读中小型文档',
  },
  grep: {
    color: '#D97706',
    icon: '🔎',
    label: 'grep — 正则匹配',
    desc: '适合在小型文档集中精确匹配',
  },
}

function SkillTag({ skill }: { skill: string }) {
  const cfg = SKILL_LABELS[skill] ?? { color: '#64748B', icon: '?', label: skill, desc: '' }
  return (
    <Tooltip title={cfg.desc}>
      <Tag
        style={{
          color: cfg.color,
          borderColor: cfg.color + '40',
          background: cfg.color + '12',
          fontWeight: 700,
          borderRadius: 6,
          fontSize: 13,
          padding: '3px 10px',
        }}
      >
        {cfg.icon} {cfg.label}
      </Tag>
    </Tooltip>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export default function Settings() {
  const [form] = Form.useForm()
  const [routing, setRouting] = useState<RoutingResponse | null>(null)
  const [routingLoading, setRoutingLoading] = useState(true)
  const [demoLoading, setDemoLoading] = useState(false)
  const [demoResult, setDemoResult] = useState<RoutingResponse | null>(null)
  const [demoError, setDemoError] = useState<string | null>(null)

  // ── Fetch routing thresholds ───────────────────────────────────────────
  const loadRouting = useCallback(async () => {
    setRoutingLoading(true)
    try {
      const res = await getRoutingSuggestion({ query_intent: 'semantic' })
      setRouting(res)
    } catch {
      // non-fatal – thresholds section will just be empty
    } finally {
      setRoutingLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRouting()
  }, [loadRouting])

  // ── Demo routing advisor ───────────────────────────────────────────────
  const handleDemo = async (values: {
    doc_ids?: string
    query_intent: 'semantic' | 'exact' | 'pattern' | 'sequential'
    query_sample?: string
  }) => {
    setDemoLoading(true)
    setDemoResult(null)
    setDemoError(null)
    try {
      const res = await getRoutingSuggestion({
        query_intent: values.query_intent,
        query_sample: values.query_sample,
      })
      setDemoResult(res)
    } catch (err) {
      setDemoError((err as Error).message)
    } finally {
      setDemoLoading(false)
    }
  }

  return (
    <div>
      {/* ── Page header ── */}
      <div style={{ marginBottom: 24 }}>
        <Title level={4} style={{ margin: 0, color: '#0F172A' }}>
          系统配置
        </Title>
        <Text type="secondary" style={{ fontSize: 13 }}>
          路由阈值参数与路由决策演示
        </Text>
      </div>

      {/* ── Routing threshold info ── */}
      <Card
        style={{
          borderRadius: 12,
          border: '1px solid #E2E8F0',
          marginBottom: 20,
        }}
        title={
          <Space>
            <ApiOutlined style={{ color: '#2563EB' }} />
            <Text strong style={{ fontSize: 14 }}>
              当前路由阈值
            </Text>
            <Tooltip title="阈值由后端 core/config.py 配置，需重启服务生效">
              <InfoCircleOutlined style={{ color: '#94A3B8', cursor: 'help' }} />
            </Tooltip>
          </Space>
        }
      >
        {routingLoading ? (
          <Row gutter={[16, 16]}>
            {[1, 2, 3].map((i) => (
              <Col key={i} xs={24} sm={8}>
                <Card style={{ borderRadius: 8, background: '#F8FAFC' }} loading />
              </Col>
            ))}
          </Row>
        ) : routing ? (
          <Row gutter={[16, 16]}>
            <Col xs={24} sm={8}>
              <Card
                style={{
                  borderRadius: 8,
                  border: '1px solid #E2E8F0',
                  background: '#F8FAFC',
                }}
              >
                <Statistic
                  title={
                    <Text style={{ fontSize: 12 }}>
                      小型文档集阈值（SMALL_DOC_THRESHOLD）
                    </Text>
                  }
                  value={routing.thresholds_applied.small_doc_threshold}
                  suffix="个文档"
                  valueStyle={{ fontSize: 24, fontWeight: 700, color: '#2563EB' }}
                />
                <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
                  ≤ 此数量 → 优先 grep / read
                </Text>
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card
                style={{
                  borderRadius: 8,
                  border: '1px solid #E2E8F0',
                  background: '#F8FAFC',
                }}
              >
                <Statistic
                  title={
                    <Text style={{ fontSize: 12 }}>
                      小型文档大小阈值（SMALL_SIZE_MB）
                    </Text>
                  }
                  value={routing.thresholds_applied.small_size_threshold_mb}
                  suffix="MB"
                  precision={1}
                  valueStyle={{ fontSize: 24, fontWeight: 700, color: '#7C3AED' }}
                />
                <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
                  总大小 ≤ 此值 → 视为小型
                </Text>
              </Card>
            </Col>
            <Col xs={24} sm={8}>
              <Card
                style={{
                  borderRadius: 8,
                  border: '1px solid #E2E8F0',
                  background: '#F8FAFC',
                }}
              >
                <Statistic
                  title={
                    <Text style={{ fontSize: 12 }}>
                      低置信度阈值（LOW_CONFIDENCE_SCORE）
                    </Text>
                  }
                  value={routing.thresholds_applied.low_confidence_score_threshold}
                  precision={2}
                  valueStyle={{ fontSize: 24, fontWeight: 700, color: '#D97706' }}
                />
                <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
                  置信度低于此值 → 触发 fallback 建议
                </Text>
              </Card>
            </Col>
          </Row>
        ) : (
          <Alert
            type="warning"
            message="无法加载路由参数，请确认后端服务已启动"
            showIcon
          />
        )}
      </Card>

      {/* ── Routing demo ── */}
      <Card
        style={{ borderRadius: 12, border: '1px solid #E2E8F0', marginBottom: 20 }}
        title={
          <Space>
            <ExperimentOutlined style={{ color: '#F97316' }} />
            <Text strong style={{ fontSize: 14 }}>
              路由决策演示
            </Text>
          </Space>
        }
      >
        <Form
          layout="vertical"
          onFinish={handleDemo}
          initialValues={{
            query_intent: 'semantic',
            query_sample: '',
          }}
        >
          <Row gutter={16}>
            <Col xs={24} sm={10}>
              <Form.Item
                name="query_intent"
                label={<Text style={{ fontSize: 13 }}>查询意图类型</Text>}
                rules={[{ required: true }]}
              >
                <Radio.Group buttonStyle="solid" style={{ width: '100%' }}>
                  <Radio.Button value="semantic" style={{ width: '25%', textAlign: 'center', fontSize: 12 }}>
                    语义
                  </Radio.Button>
                  <Radio.Button value="exact" style={{ width: '25%', textAlign: 'center', fontSize: 12 }}>
                    精确
                  </Radio.Button>
                  <Radio.Button value="pattern" style={{ width: '25%', textAlign: 'center', fontSize: 12 }}>
                    模式
                  </Radio.Button>
                  <Radio.Button value="sequential" style={{ width: '25%', textAlign: 'center', fontSize: 12 }}>
                    顺序
                  </Radio.Button>
                </Radio.Group>
              </Form.Item>
            </Col>
            <Col xs={24} sm={14}>
              <Form.Item
                name="query_sample"
                label={<Text style={{ fontSize: 13 }}>示例查询（可选）</Text>}
              >
                <input
                  placeholder="输入示例查询文本…"
                  style={{
                    width: '100%',
                    padding: '7px 11px',
                    borderRadius: 6,
                    border: '1px solid #D1D5DB',
                    fontSize: 13,
                    outline: 'none',
                  }}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              icon={<BulbOutlined />}
              loading={demoLoading}
              style={{ borderRadius: 8 }}
            >
              获取路由建议
            </Button>
          </Form.Item>
        </Form>

        {/* Demo error */}
        {demoError && (
          <Alert
            type="error"
            message={demoError}
            closable
            onClose={() => setDemoError(null)}
            style={{ marginTop: 16, borderRadius: 8 }}
          />
        )}

        {/* Demo result */}
        {demoResult && !demoLoading && (
          <div
            style={{
              marginTop: 20,
              padding: '16px 20px',
              background: '#F8FAFC',
              borderRadius: 8,
              border: '1px solid #E2E8F0',
            }}
          >
            <Row gutter={[16, 12]} align="middle">
              <Col xs={24} sm={12}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                  推荐技能
                </Text>
                <Space>
                  <SkillTag skill={demoResult.recommended_skill} />
                  <Text style={{ fontSize: 12, color: '#64748B' }}>
                    置信度：
                    <Text
                      strong
                      style={{
                        color:
                          demoResult.confidence >= 0.8
                            ? '#16A34A'
                            : demoResult.confidence >= 0.65
                            ? '#D97706'
                            : '#DC2626',
                      }}
                    >
                      {(demoResult.confidence * 100).toFixed(0)}%
                    </Text>
                  </Text>
                </Space>

                {demoResult.fallback_skill && (
                  <div style={{ marginTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                      备选技能
                    </Text>
                    <SkillTag skill={demoResult.fallback_skill} />
                  </div>
                )}
              </Col>

              <Col xs={24} sm={12}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                  决策依据
                </Text>
                <Paragraph
                  style={{
                    margin: 0,
                    fontSize: 13,
                    color: '#334155',
                    lineHeight: 1.6,
                  }}
                >
                  {demoResult.reason}
                </Paragraph>
              </Col>

              {demoResult.low_confidence_note && (
                <Col xs={24}>
                  <Alert
                    type="warning"
                    message={demoResult.low_confidence_note}
                    showIcon
                    icon={<BulbOutlined />}
                    style={{ borderRadius: 6 }}
                  />
                </Col>
              )}
            </Row>

            <Divider style={{ margin: '16px 0' }} />

            {/* Doc stats */}
            <Row gutter={[12, 8]}>
              <Col span={24}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  文档库快照
                </Text>
              </Col>
              {[
                { label: '总文档数', value: demoResult.doc_stats.total_docs },
                { label: '已索引', value: demoResult.doc_stats.indexed_docs },
                { label: '未索引', value: demoResult.doc_stats.unindexed_docs },
                { label: '总 Chunk', value: demoResult.doc_stats.total_chunks },
              ].map((stat) => (
                <Col key={stat.label} xs={12} sm={6}>
                  <div
                    style={{
                      background: '#fff',
                      borderRadius: 6,
                      padding: '8px 12px',
                      border: '1px solid #E2E8F0',
                    }}
                  >
                    <Text type="secondary" style={{ fontSize: 11, display: 'block' }}>
                      {stat.label}
                    </Text>
                    <Text strong style={{ fontSize: 18, color: '#0F172A' }}>
                      {stat.value}
                    </Text>
                  </div>
                </Col>
              ))}
            </Row>
          </div>
        )}
      </Card>

      {/* ── About / API docs ── */}
      <Card
        style={{ borderRadius: 12, border: '1px solid #E2E8F0' }}
        title={
          <Space>
            <RocketOutlined style={{ color: '#2563EB' }} />
            <Text strong style={{ fontSize: 14 }}>
              关于 DocSearch
            </Text>
          </Space>
        }
      >
        <Paragraph style={{ margin: 0, fontSize: 13, color: '#475569', lineHeight: 1.8 }}>
          DocSearch 是一个 AI Agent 文档检索系统，提供三种检索技能（query / read / grep），
          通过自动路由建议选择最优策略。后端基于 FastAPI + PostgreSQL (pgvector + BM25) + BAAI/bge-m3 嵌入模型。
        </Paragraph>
        <div style={{ marginTop: 16 }}>
          <Space wrap>
            <Tag color="blue" style={{ borderRadius: 6 }}>
              FastAPI
            </Tag>
            <Tag color="purple" style={{ borderRadius: 6 }}>
              pgvector
            </Tag>
            <Tag color="cyan" style={{ borderRadius: 6 }}>
              pg_search (BM25)
            </Tag>
            <Tag color="orange" style={{ borderRadius: 6 }}>
              BAAI/bge-m3
            </Tag>
            <Tag color="green" style={{ borderRadius: 6 }}>
              LangChain Tools
            </Tag>
            <Tag color="gold" style={{ borderRadius: 6 }}>
              Celery + Redis
            </Tag>
            <Tag color="lime" style={{ borderRadius: 6 }}>
              MinIO
            </Tag>
            <Tag color="red" style={{ borderRadius: 6 }}>
              React + Ant Design 5
            </Tag>
          </Space>
        </div>
        <div style={{ marginTop: 16 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            API 文档：
          </Text>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: 12, color: '#2563EB', marginLeft: 6 }}
          >
            http://localhost:8000/docs (Swagger UI)
          </a>
        </div>
      </Card>
    </div>
  )
}
