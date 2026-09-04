import { useEffect, useState } from 'react'
import { Button, Empty, List, Typography } from 'antd'
import { Link } from 'react-router-dom'
import client from '../api/client'

type CartData = { items: { product_name: string; variant_name: string; quantity: number; price: number; brand: string }[]; total_amount: number }

export default function Cart() {
  const [data, setData] = useState<CartData | null>(null)
  const [failed, setFailed] = useState(false)
  const load = () => client.get<CartData>('/shop/cart').then((response) => { setData(response.data); setFailed(false) }).catch(() => setFailed(true))
  useEffect(() => { load() }, [])
  if (failed) return <main className="page-wrap"><Empty description="购物车加载失败"><Button onClick={load}>重新加载</Button></Empty></main>
  if (!data) return <main className="page-wrap shop-loading" aria-live="polite">正在读取购物车</main>
  return <main className="page-wrap shop-subpage"><p className="shop-eyebrow">SHOPPING BAG</p><h1>购物车</h1>{data.items.length ? <section className="cart-panel"><List dataSource={data.items} renderItem={(item) => <List.Item className="cart-line"><div><strong>{item.brand} · {item.product_name}</strong><span>{item.variant_name} · 数量 {item.quantity}</span></div><b>¥{(item.price * item.quantity).toFixed(2)}</b></List.Item>} /><footer className="cart-summary"><div><span>订单合计</span><Typography.Title level={3}>¥{data.total_amount.toFixed(2)}</Typography.Title></div><Link to="/shop/checkout"><Button type="primary" size="large">去结算</Button></Link></footer></section> : <Empty className="shop-empty" description="购物车还是空的"><Link to="/shop"><Button type="primary">去挑选商品</Button></Link></Empty>}</main>
}
