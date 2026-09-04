import { FileTextOutlined, HomeOutlined, LogoutOutlined, SafetyCertificateOutlined, ShoppingCartOutlined } from '@ant-design/icons'
import { Badge, Button, Layout, Menu, Space } from 'antd'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { getSessionUser } from '../types/auth'

const { Header, Content } = Layout

const navigation = [
  { key: '/shop', icon: <HomeOutlined />, label: '商城首页' },
  { key: '/shop/cart', icon: <ShoppingCartOutlined />, label: '购物车' },
  { key: '/shop/orders', icon: <FileTextOutlined />, label: '我的订单' },
  { key: '/shop/returns', icon: <SafetyCertificateOutlined />, label: '退款售后' },
]

export default function CustomerShell() {
  const nav = useNavigate()
  const location = useLocation()
  const selectedKey = navigation.some((item) => location.pathname === item.key) ? location.pathname : '/shop'
  const logout = () => {
    localStorage.removeItem('token')
    nav('/login', { replace: true })
  }

  if (getSessionUser()?.role !== 'customer') return <Navigate to="/" replace />

  return (
    <Layout className="customer-shell">
      <Header className="customer-header">
        <button className="customer-brand" type="button" onClick={() => nav('/shop')} aria-label="返回商城首页">
          <span className="customer-brand__mark" aria-hidden="true">M</span>
          <span>品牌优选商城</span>
        </button>
        <Menu className="customer-nav" mode="horizontal" selectedKeys={[selectedKey]} items={navigation} onClick={({ key }) => nav(key)} />
        <Space className="customer-header__actions">
          <Badge size="small" offset={[-2, 4]}><Button aria-label="打开购物车" type="text" icon={<ShoppingCartOutlined />} onClick={() => nav('/shop/cart')}>购物车</Button></Badge>
          <Button aria-label="退出登录" type="text" icon={<LogoutOutlined />} onClick={logout}>退出</Button>
        </Space>
      </Header>
      <Content className="customer-content"><Outlet /></Content>
    </Layout>
  )
}
