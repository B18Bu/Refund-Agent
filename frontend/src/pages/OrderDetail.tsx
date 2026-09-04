import { useEffect, useState } from 'react'
import { Alert, Button, Card, Empty, Form, Input, List, Modal, Select, Upload, message } from 'antd'
import type { UploadFile } from 'antd'
import { useNavigate, useParams } from 'react-router-dom'
import client from '../api/client'
import type { Order } from '../types/shop'

export default function OrderDetail() {
  const { id } = useParams(); const nav = useNavigate(); const [order, setOrder] = useState<Order>(); const [open, setOpen] = useState(false); const [files, setFiles] = useState<UploadFile[]>([])
  useEffect(() => { client.get(`/shop/orders/${id}`).then((response) => setOrder(response.data)).catch(() => undefined) }, [id])
  if (!order) return <main className="page-wrap"><Empty description="订单不存在或暂时无法加载" /></main>
  const submit = (value: { order_item_id: number; reason: string; description?: string }) => client.post(`/shop/orders/${order.id}/returns`, { ...value, evidence_paths: files.map((file) => file.name) }, { headers: { 'X-Idempotency-Key': crypto.randomUUID() } }).then(() => { message.success('退款申请已提交'); nav('/shop/returns') }).catch((error) => message.error(error.response?.data?.detail || '提交失败'))
  return <main className="page-wrap shop-subpage"><p className="shop-eyebrow">ORDER DETAIL</p><h1>订单详情</h1><Card className="order-card"><div className="order-card__summary"><span>订单号 {order.order_no}</span><strong>¥{order.total_amount.toFixed(2)}</strong></div><p>订单状态：{order.status}</p><List dataSource={order.items} renderItem={(item) => <List.Item>{String(item.product_snapshot_json.name)} × {item.quantity}<b>¥{item.unit_price.toFixed(2)}</b></List.Item>} /><Button type="primary" disabled={order.status !== 'PAID_SIMULATED'} onClick={() => setOpen(true)}>申请退款</Button></Card><Modal title="申请退款" open={open} footer={null} onCancel={() => setOpen(false)}><Alert type="info" showIcon message="请至少上传一张商品或问题凭证" description="如凭证无法识别或风险条件不满足，申请会转为人工审核。" /><Form layout="vertical" onFinish={submit}><Form.Item name="order_item_id" label="订单商品" rules={[{ required: true, message: '请选择商品' }]}><Select options={order.items.map((item) => ({ value: item.id, label: String(item.product_snapshot_json.name) }))} /></Form.Item><Form.Item name="reason" label="退款原因" rules={[{ required: true, message: '请填写退款原因' }]}><Input /></Form.Item><Form.Item name="description" label="问题说明"><Input.TextArea maxLength={4000} rows={3} /></Form.Item><Form.Item label="商品/问题凭证" required><Upload accept="image/*" beforeUpload={() => false} fileList={files} maxCount={3} onChange={({ fileList }) => setFiles(fileList)}><Button>选择图片</Button></Upload></Form.Item><Button htmlType="submit" type="primary" disabled={files.length === 0}>提交退款申请</Button></Form></Modal></main>
}
