import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

const theme = {
  token: {
    colorPrimary: '#2563EB',
    colorLink: '#2563EB',
    colorSuccess: '#16A34A',
    colorWarning: '#D97706',
    colorError: '#DC2626',
    colorBgBase: '#F8FAFC',
    colorTextBase: '#1E293B',
    fontFamily:
      "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    borderRadius: 8,
    fontSize: 14,
    lineHeight: 1.6,
    controlHeight: 36,
    motionDurationMid: '0.2s',
    motionDurationSlow: '0.3s',
    boxShadow:
      '0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.06)',
    boxShadowSecondary:
      '0 4px 6px -1px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.06)',
  },
  components: {
    Layout: {
      siderBg: '#0F172A',
      triggerBg: '#1E293B',
    },
    Menu: {
      darkItemBg: '#0F172A',
      darkSubMenuItemBg: '#162032',
      darkItemSelectedBg: '#2563EB',
      darkItemHoverBg: 'rgba(37,99,235,0.15)',
    },
    Card: {
      borderRadiusLG: 12,
    },
    Button: {
      borderRadius: 8,
      controlHeight: 38,
    },
  },
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN} theme={theme}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
