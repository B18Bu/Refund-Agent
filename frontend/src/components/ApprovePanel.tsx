import { Button, Input, Space, message } from 'antd'
import { useState } from 'react'
import client from '../api/client'

export default function ApprovePanel({ ticketId, onDone }: { ticketId: number; onDone: () => void }) {
  const [comment, setComment] = useState('')
  const [loading, setLoading] = useState(false)

  const act = async (action: 'APPROVE' | 'REJECT') => {
    setLoading(true)
    try {
      await client.post(`/tickets/${ticketId}/approve`, { action, comment })
      message.success(action === 'APPROVE' ? '已批准' : '已拒绝')
      onDone()
    } catch (e: any) {
      message.error(e.response?.data?.detail || '操作失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Space>
      <Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="审批意见（可选）" style={{ width: 240 }} />
      <Button type="primary" loading={loading} onClick={() => act('APPROVE')}>APPROVE 同意</Button>
      <Button danger loading={loading} onClick={() => act('REJECT')}>REJECT 拒绝</Button>
    </Space>
  )
}
