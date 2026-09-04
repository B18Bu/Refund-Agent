import { useEffect, useState } from 'react'
import { Badge, Button, Layout, Menu, Space, Tag } from 'antd'
import {
  DashboardOutlined,
  FileTextOutlined,
  FundOutlined,
  LineChartOutlined,
  MonitorOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
  ReloadOutlined,
  LogoutOutlined,
  ShoppingOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import client from '../api/client'
import { getSessionUser } from '../types/auth'

const { Header, Sider, Content } = Layout

type TicketRow = { status: string; outcome: string }

export default function AppShell() {
  const nav = useNavigate()
  const location = useLocation()
  const user = getSessionUser()
  const [collapsed, setCollapsed] = useState(false)
  const [counts, setCounts] = useState({ failed: 0, pending: 0 })

  useEffect(() => {
    if (user?.role !== 'sv') return
    let mounted = true
    const loadCounts = async () => {
      try {
        const { data } = await client.get<TicketRow[]>('/tickets')
        if (!mounted) return
        setCounts({
          failed: data.filter((row) => row.outcome === 'FAILED').length,
          pending: data.filter((row) => row.status === 'SUSPENDED').length,
        })
      } catch {
        if (mounted) setCounts({ failed: 0, pending: 0 })
      }
    }
    loadCounts()
    const timer = window.setInterval(loadCounts, 5000)
    return () => {
      mounted = false
      window.clearInterval(timer)
    }
  }, [user?.role])

  if (!user) return null

  const items = user.role === 'sv'
    ? [
        { key: '/monitor', icon: <MonitorOutlined />, label: <Badge className="app-nav-badge" styles={{ root: { color: 'inherit' } }} count={counts.failed} offset={[8, 0]}>实时监控</Badge> },
        { key: '/workspace', icon: <DashboardOutlined />, label: '退款工作台' },
        { key: '/approvals', icon: <SafetyCertificateOutlined />, label: <Badge className="app-nav-badge" styles={{ root: { color: 'inherit' } }} count={counts.pending} color="#d46b08" offset={[8, 0]}>待人工审批</Badge> },
        { key: '/process', icon: <FileTextOutlined />, label: '退款流程总览' },
        { key: '/screen', icon: <FundOutlined />, label: '数据大屏' },
        { key: '/evaluations', icon: <LineChartOutlined />, label: 'Agent 评测' },
        { key: '/security-governance', icon: <SafetyCertificateOutlined />, label: '安全治理中心' },
      ]
    : [
        { key: '/shop', icon: <ShoppingOutlined />, label: '电商首页' },
        { key: '/shop/cart', icon: <ShoppingOutlined />, label: '购物车' },
        { key: '/shop/orders', icon: <FileTextOutlined />, label: '我的订单' },
        { key: '/shop/returns', icon: <SafetyCertificateOutlined />, label: '我的退单' },
        { key: '/workspace', icon: <DashboardOutlined />, label: '退款工作台' },
        { key: '/my-tickets', icon: <TeamOutlined />, label: '我的申请' },
        { key: '/process', icon: <FileTextOutlined />, label: '退款流程总览' },
      ]

  const currentKey = items.some((item) => item.key === location.pathname) ? location.pathname : ''
  const logout = () => {
    localStorage.removeItem('token')
    nav('/login', { replace: true })
  }

  return (
    <Layout className="app-shell">
      <Sider className="app-sider" collapsible collapsed={collapsed} collapsedWidth={64} onCollapse={setCollapsed} theme="dark" breakpoint="lg">
        <div className="app-brand" style={{ paddingInline: collapsed ? 8 : 18 }}>
          退赔决策控制台
        </div>
        <Menu className="app-nav" aria-label="主导航" theme="dark" mode="inline" selectedKeys={currentKey ? [currentKey] : []} items={items} onClick={({ key }) => nav(key)} />
      </Sider>
      <Layout className="app-main">
        <Header className="app-header">
          <Tag color={user.role === 'sv' ? 'blue' : 'green'}>{user.role === 'sv' ? '主管' : '客服'}</Tag>
          <Space className="app-header__actions">
            <Button aria-label="刷新数据" icon={<ReloadOutlined />} onClick={() => window.dispatchEvent(new Event('refund-refresh'))}><span className="app-header__action-label">刷新数据</span></Button>
            <Button aria-label="退出登录" icon={<LogoutOutlined />} onClick={logout}><span className="app-header__action-label">退出登录</span></Button>
          </Space>
        </Header>
        <Content className="app-content"><Outlet /></Content>
      </Layout>
    </Layout>
  )
}
