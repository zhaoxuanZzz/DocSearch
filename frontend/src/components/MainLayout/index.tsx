import {
  DatabaseOutlined,
  SearchOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import { Badge, Layout, Menu, Typography } from 'antd'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

const { Sider, Content } = Layout
const { Text } = Typography

const NAV_ITEMS = [
  { key: '/documents', icon: <DatabaseOutlined />, label: '文档库' },
  { key: '/search', icon: <SearchOutlined />, label: '检索测试' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统配置' },
]

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const selectedKey =
    NAV_ITEMS.find((item) => location.pathname.startsWith(item.key))?.key ??
    '/documents'

  return (
    <Layout style={{ minHeight: '100dvh' }}>
      {/* ── Sidebar ── */}
      <Sider
        width={220}
        theme="dark"
        style={{
          position: 'fixed',
          insetBlockStart: 0,
          insetInlineStart: 0,
          height: '100dvh',
          overflowY: 'auto',
          zIndex: 100,
        }}
      >
        {/* Logo / Brand */}
        <div
          style={{
            height: 64,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '0 20px',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: 'linear-gradient(135deg, #2563EB 0%, #3B82F6 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              boxShadow: '0 0 0 2px rgba(37,99,235,0.3)',
            }}
          >
            <SearchOutlined style={{ color: '#fff', fontSize: 16 }} />
          </div>
          <div>
            <Text
              strong
              style={{
                color: '#F8FAFC',
                fontSize: 15,
                display: 'block',
                lineHeight: 1.2,
              }}
            >
              DocSearch
            </Text>
            <Text style={{ color: '#94A3B8', fontSize: 11 }}>Agent 文档检索</Text>
          </div>
        </div>

        {/* Navigation */}
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          onClick={({ key }) => navigate(key)}
          style={{ marginTop: 8, borderRight: 'none' }}
          items={NAV_ITEMS.map((item) => ({
            key: item.key,
            icon: item.icon,
            label: item.label,
          }))}
        />

        {/* Footer status */}
        <div
          style={{
            position: 'absolute',
            bottom: 16,
            left: 0,
            right: 0,
            padding: '0 20px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Badge status="success" />
          <Text style={{ color: '#64748B', fontSize: 12 }}>服务运行中</Text>
        </div>
      </Sider>

      {/* ── Main Content ── */}
      <Layout style={{ marginInlineStart: 220 }}>
        <Content
          style={{
            padding: '24px 28px',
            minHeight: '100dvh',
            background: '#F8FAFC',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
