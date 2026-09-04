import { useEffect, useState } from 'react'
import { Empty, List, Tag } from 'antd'
import { Link } from 'react-router-dom'
import client from '../api/client'
import type { Order } from '../types/shop'

export default function Orders() {
  const [rows, setRows] = useState<Order[]>([])
  useEffect(() => { client.get('/shop/orders').then((response) => setRows(response.data)).catch(() => undefined) }, [])
  return <main className="page-wrap shop-subpage storeflow-page"><p className="shop-eyebrow">MY ORDERS</p><h1>我的订单</h1>{rows.length ? <List className="storeflow-orders" dataSource={rows} renderItem={(order) => <List.Item><div><Link to={`/shop/orders/${order.id}`}>{order.order_no}</Link><span>订单状态</span>{order.status === 'PAID_SIMULATED' ? <Link className="storeflow-orders__return" to={`/shop/orders/${order.id}`}>申请退单</Link> : <span>支付完成后可申请退单</span>}</div><Tag>{order.status}</Tag><strong>¥{order.total_amount.toFixed(2)}</strong></List.Item>} /> : <Empty className="shop-empty" description="暂无订单" />}</main>
}
