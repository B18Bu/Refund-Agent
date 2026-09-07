import { CustomerServiceOutlined, FileTextOutlined, LogoutOutlined, MenuOutlined, SearchOutlined, SafetyCertificateOutlined, ShoppingCartOutlined } from '@ant-design/icons'
import { Badge, Button, Input, Layout } from 'antd'
import { FormEvent, useState } from 'react'
import { Link, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { getSessionUser } from '../types/auth'

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
        <nav className="customer-utility-nav" aria-label="商城工具栏">
          <span>您好，欢迎来到品牌优选商城</span>
          <div><Link to="/shop/orders">我的订单</Link><Link to="/shop/returns">退款售后</Link><Link to="/shop/assistant">商品咨询</Link><Link to="/shop/privacy">隐私偏好</Link><Link to="/shop/cart">购物车</Link><button type="button" onClick={logout}><LogoutOutlined aria-hidden="true" />退出登录</button></div>
        </nav>
        <div className="customer-search-row">
          <Link className="customer-brand" to="/shop" aria-label="返回商城首页">
            <span className="customer-brand__mark" aria-hidden="true">M</span>
            <span><b>品牌优选</b><small>BRAND SELECT MALL</small></span>
          </Link>
          <form className="customer-search" role="search" aria-label="搜索商城商品" onSubmit={search}>
            <Input aria-label="搜索商城商品" placeholder="搜索手机、耳机、数据线等官方商品" value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} suffix={<SearchOutlined aria-hidden="true" />} />
            <Button htmlType="submit" type="primary">搜索</Button>
          </form>
          <div className="customer-header__actions">
            <Link to="/shop/orders"><FileTextOutlined aria-hidden="true" />我的订单</Link>
            <Badge size="small" offset={[-2, 3]}><Link to="/shop/cart"><ShoppingCartOutlined aria-hidden="true" />购物车</Link></Badge>
          </div>
        </div>
        <nav className="customer-main-nav" aria-label="商城主导航">
          <Link className="customer-main-nav__categories" to="/shop"><MenuOutlined aria-hidden="true" />全部商品分类</Link>
          <Link to="/shop">商城首页</Link><Link to="/shop?keyword=手机">手机数码</Link><Link to="/shop?keyword=耳机">耳机配件</Link><Link to="/shop/returns"><SafetyCertificateOutlined aria-hidden="true" />售后服务</Link><Link to="/shop/assistant"><CustomerServiceOutlined aria-hidden="true" />商品咨询</Link><Link to="/shop/orders"><CustomerServiceOutlined aria-hidden="true" />订单服务</Link>
        </nav>
      </Header>
      <Content className="customer-content"><Outlet /></Content>
    </Layout>
  )
}
