import { CustomerServiceOutlined, LogoutOutlined, MenuOutlined, SearchOutlined, SafetyCertificateOutlined, ShoppingCartOutlined, UserOutlined } from '@ant-design/icons'
import { Badge, Button, Input, Layout } from 'antd'
import { FormEvent, useState } from 'react'
import { Link, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { getSessionUser } from '../types/auth'
import CustomerAssistant from '../pages/CustomerAssistant'

const { Header, Content } = Layout

export default function CustomerShell() {
  const nav = useNavigate()
  const [searchTerm, setSearchTerm] = useState('')
  const logout = () => {
    localStorage.removeItem('token')
    nav('/login', { replace: true })
  }
  const search = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    nav(searchTerm.trim() ? `/shop?keyword=${encodeURIComponent(searchTerm.trim())}` : '/shop')
  }

  if (getSessionUser()?.role !== 'customer') return <Navigate to="/" replace />

  return (
    <Layout className="customer-shell">
      <Header className="customer-header">
        <div className="customer-search-row">
          <Link className="customer-brand" to="/shop" aria-label="返回商城首页">
            <span className="customer-brand__mark" aria-hidden="true">M</span>
            <span><b>品牌优选</b><small>BRAND SELECT MALL</small></span>
          </Link>
          <form className="customer-search" role="search" aria-label="搜索商城商品" onSubmit={search}>
            <Input aria-label="搜索商城商品" placeholder="搜索商品、型号或配件" value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} suffix={<SearchOutlined aria-hidden="true" />} />
            <Button htmlType="submit" type="primary">搜索</Button>
          </form>
          <div className="customer-header__actions">
            <Link to="/shop/account"><UserOutlined aria-hidden="true" />我的</Link>
            <Badge size="small" offset={[-2, 3]}><Link to="/shop/cart"><ShoppingCartOutlined aria-hidden="true" />购物车</Link></Badge>
            <button type="button" onClick={logout}><LogoutOutlined aria-hidden="true" />退出登录</button>
          </div>
        </div>
        <nav className="customer-main-nav" aria-label="商城主导航">
          <Link className="customer-main-nav__categories" to="/shop"><MenuOutlined aria-hidden="true" />全部商品分类</Link>
          <Link to="/shop">商城首页</Link><Link to="/shop?keyword=手机">手机数码</Link><Link to="/shop?keyword=耳机">耳机配件</Link><Link to="/shop/returns"><SafetyCertificateOutlined aria-hidden="true" />售后服务</Link><Link to="/shop/orders"><CustomerServiceOutlined aria-hidden="true" />订单服务</Link>
        </nav>
      </Header>
      <Content className="customer-content"><Outlet /></Content>
      <CustomerAssistant />
    </Layout>
  )
}
