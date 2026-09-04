import { useEffect, useState } from 'react'
import { Alert, Button, Empty, Radio, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import client from '../api/client'

type Address = { id: number; recipient_name: string; phone: string; province: string; city: string; district: string; detail: string; is_default: boolean }

export default function Checkout() {
  const [addresses, setAddresses] = useState<Address[]>([])
  const [address, setAddress] = useState<number>()
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const nav = useNavigate()
  useEffect(() => { client.get<Address[]>('/shop/addresses').then((response) => { setAddresses(response.data); setAddress(response.data.find((item) => item.is_default)?.id ?? response.data[0]?.id) }).catch(() => message.error('收货地址加载失败')).finally(() => setLoading(false)) }, [])
  const submit = async () => {
    if (!address) { message.warning('请先选择收货地址'); return }
    setSubmitting(true)
    try { const { data } = await client.post('/shop/orders', { address_id: address }, { headers: { 'X-Idempotency-Key': crypto.randomUUID() } }); await client.post(`/shop/orders/${data.id}/simulate-pay`); message.success('订单已创建，模拟支付成功'); nav('/shop/orders') } catch (error: any) { message.error(error.response?.data?.detail || '订单提交失败，请确认购物车和地址') } finally { setSubmitting(false) }
  }
  return <main className="page-wrap shop-subpage"><p className="shop-eyebrow">CHECKOUT</p><h1>确认订单</h1><section className="checkout-panel"><Typography.Title level={3}>选择收货地址</Typography.Title>{loading ? <p>正在加载地址…</p> : addresses.length ? <Radio.Group className="address-list" value={address} onChange={(event) => setAddress(event.target.value)}>{addresses.map((item) => <Radio className="address-card" value={item.id} key={item.id}><strong>{item.recipient_name} {item.phone}</strong><span>{item.province}{item.city}{item.district}{item.detail}</span>{item.is_default && <em>默认地址</em>}</Radio>)}</Radio.Group> : <Empty description="暂无收货地址" />}</section><Alert className="checkout-notice" type="info" showIcon message="提交订单后将立即完成模拟支付" description="本平台不处理真实支付信息；订单金额以服务端返回结果为准。" /><Button type="primary" size="large" block disabled={!address} loading={submitting} onClick={submit}>提交订单并模拟支付</Button></main>
}
