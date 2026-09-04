import { useEffect, useState } from 'react'
import { Alert, Button, Checkbox, Drawer, Empty, Form, Input, Radio, Typography, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import client from '../api/client'

type Address = { id: number; recipient_name: string; phone: string; province: string; city: string; district: string; detail: string; is_default: boolean }
type AddressInput = Omit<Address, 'id'>

export default function Checkout() {
  const [addresses, setAddresses] = useState<Address[]>([])
  const [address, setAddress] = useState<number>()
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [savingAddress, setSavingAddress] = useState(false)
  const [form] = Form.useForm<AddressInput>()
  const nav = useNavigate()
  useEffect(() => { client.get<Address[]>('/shop/addresses').then((response) => { setAddresses(response.data); setAddress(response.data.find((item) => item.is_default)?.id ?? response.data[0]?.id) }).catch(() => message.error('收货地址加载失败')).finally(() => setLoading(false)) }, [])
  const submit = async () => {
    if (!address) { message.warning('请先选择收货地址'); return }
    setSubmitting(true)
    try { const { data } = await client.post('/shop/orders', { address_id: address }, { headers: { 'X-Idempotency-Key': crypto.randomUUID() } }); await client.post(`/shop/orders/${data.id}/simulate-pay`); message.success('订单已创建，模拟支付成功'); nav('/shop/orders') } catch (error: any) { message.error(error.response?.data?.detail || '订单提交失败，请确认购物车和地址') } finally { setSubmitting(false) }
  }
  const createAddress = async (values: AddressInput) => {
    setSavingAddress(true)
    try {
      const { data } = await client.post<Address>('/shop/addresses', values)
      setAddresses((current) => [...current, data])
      setAddress(data.id)
      setDrawerOpen(false)
      form.resetFields()
      message.success('收货地址已创建')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '收货地址保存失败')
    } finally {
      setSavingAddress(false)
    }
  }
  return <main className="page-wrap shop-subpage storeflow-page"><p className="shop-eyebrow">CHECKOUT</p><h1>确认订单</h1><p className="storeflow-page__intro">请确认收货信息后提交订单。</p><section className="checkout-panel storeflow-panel"><div className="checkout-panel__heading"><Typography.Title level={3}>选择收货地址</Typography.Title><Button type="primary" onClick={() => setDrawerOpen(true)}>新建收货地址</Button></div>{loading ? <p>正在加载地址…</p> : addresses.length ? <Radio.Group className="address-list" value={address} onChange={(event) => setAddress(event.target.value)}>{addresses.map((item) => <Radio aria-label={`${item.recipient_name} ${item.phone} ${item.province}${item.city}${item.district}${item.detail}${item.is_default ? ' 默认地址' : ''}`} className="address-card" value={item.id} key={item.id}><strong>{item.recipient_name} {item.phone}</strong><span>{item.province}{item.city}{item.district}{item.detail}</span>{item.is_default && <em>默认地址</em>}</Radio>)}</Radio.Group> : <Empty description="暂无收货地址，请先创建后再提交订单" />}</section><Drawer title="新建收货地址" open={drawerOpen} onClose={() => setDrawerOpen(false)} destroyOnClose><Form form={form} layout="vertical" initialValues={{ is_default: addresses.length === 0 }} onFinish={createAddress}><Form.Item label="收件人" name="recipient_name" rules={[{ required: true, message: '请输入收件人' }]}><Input /></Form.Item><Form.Item label="手机号" name="phone" rules={[{ required: true, message: '请输入手机号' }, { pattern: /^1\d{10}$/, message: '请输入 11 位手机号' }]}><Input inputMode="numeric" /></Form.Item><div className="address-form__region"><Form.Item label="省" name="province" rules={[{ required: true, message: '请输入省' }]}><Input /></Form.Item><Form.Item label="市" name="city" rules={[{ required: true, message: '请输入市' }]}><Input /></Form.Item><Form.Item label="区" name="district" rules={[{ required: true, message: '请输入区' }]}><Input /></Form.Item></div><Form.Item label="详细地址" name="detail" rules={[{ required: true, message: '请输入详细地址' }]}><Input.TextArea rows={3} /></Form.Item><Form.Item name="is_default" valuePropName="checked"><Checkbox>设为默认地址</Checkbox></Form.Item><Button htmlType="submit" type="primary" block loading={savingAddress}>保存地址</Button></Form></Drawer><Alert className="checkout-notice" type="info" showIcon message="模拟支付说明" description="提交订单后将立即完成模拟支付；本平台不处理真实支付信息，订单金额以服务端返回结果为准。" /><Button type="primary" size="large" block disabled={!address} loading={submitting} onClick={submit}>提交订单并模拟支付</Button></main>
}
