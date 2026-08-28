import { useEffect, useState } from 'react'
import { Badge, Button, Layout, Menu, Space, Tag } from 'antd'
import {
  DashboardOutlined,
  FileTextOutlined,
  FundOutlined,
  MonitorOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
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
        { key: '/monitor', icon: <MonitorOutlined />, label: <Badge count={counts.failed} offset={[8, 0]} style={{ color: 'inherit' }}>实时监控</Badge> },
        { key: '/workspace', icon: <DashboardOutlined />, label: '退款工作台' },
        { key: '/approvals', icon: <SafetyCertificateOutlined />, label: <Badge count={counts.pending} color="#fa8c16" offset={[8, 0]} style={{ color: 'inherit' }}>待人工审批</Badge> },
        { key: '/process', icon: <FileTextOutlined />, label: '退款流程总览' },
        { key: '/screen', icon: <FundOutlined />, label: '数据大屏' },
      ]
    : [
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
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed} theme="dark" breakpoint="lg">
        <div style={{ color: '#fff', fontWeight: 700, padding: collapsed ? '20px 8px' : '20px 18px', whiteSpace: 'nowrap', overflow: 'hidden' }}>
          退赔决策控制台
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={currentKey ? [currentKey] : []} items={items} onClick={({ key }) => nav(key)} />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0 24px', borderBottom: '1px solid #f0f0f0' }}>
          <Tag color={user.role === 'sv' ? 'blue' : 'green'}>{user.role === 'sv' ? '主管' : '客服'}</Tag>
          <Space>
            <Button onClick={() => window.dispatchEvent(new Event('refund-refresh'))}>刷新数据</Button>
            <Button onClick={logout}>退出登录</Button>
          </Space>
        </Header>
        <Content style={{ padding: 24, minWidth: 0, background: '#f5f7fa' }}><Outlet /></Content>
      </Layout>
    </Layout>
  )
}
