import { useEffect, useState } from 'react'
import { Table, Button, InputNumber, Tag, message, Space, Typography } from 'antd'
import client from '../api/client'
import { useNavigate } from 'react-router-dom'

type Row = {
  id: number
  ticket_no: string
  amount: number
  status: string
  outcome: string
  fraud_score: number | null
  sentiment: string | null
  error_code: string | null
  created_at: string | null
}

const statusColor: Record<string, string> = {
  RUNNING: 'blue',
  SUSPENDED: 'gold',
  COMPLETED: 'green',
}

const outcomeColor: Record<string, string> = {
  PENDING: 'default',
  AUTO_REFUNDED: 'cyan',
  APPROVED: 'green',
  REJECTED: 'red',
  FAILED: 'volcano',
}

export default function Dashboard() {
  const [rows, setRows] = useState<Row[]>([])
  const [amount, setAmount] = useState<number>(128)
  const [loading, setLoading] = useState(false)
  const nav = useNavigate()

  const load = async () => {
    const { data } = await client.get('/tickets')
    setRows(data)
  }
  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  const create = async () => {
    setLoading(true)
    try {
      await client.post(
        '/tickets',
        { amount, image_paths: [] },
        { headers: { 'X-Idempotency-Key': crypto.randomUUID() } },
      )
      message.success('已提交申请')
      load()
    } catch (e: any) {
      message.error(e.response?.data?.detail || '提交失败')
    } finally {
      setLoading(false)
    }
  }

  const cols = [
    { title: '工单号', dataIndex: 'ticket_no' },
    { title: '金额', dataIndex: 'amount', render: (v: number) => `¥${v}` },
    { title: '状态', dataIndex: 'status', render: (v: string) => <Tag color={statusColor[v]}>{v}</Tag> },
    { title: '结果', dataIndex: 'outcome', render: (v: string) => <Tag color={outcomeColor[v]}>{v}</Tag> },
    { title: '欺诈分', dataIndex: 'fraud_score', render: (v: number | null) => v ?? '-' },
    { title: '舆情', dataIndex: 'sentiment', render: (v: string | null) => v ?? '-' },
    { title: '错误', dataIndex: 'error_code', render: (v: string | null) => v ?? '-' },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Title level={4} style={{ margin: 0 }}>退赔工单工作台</Typography.Title>
        <Button onClick={() => nav('/screen')}>进入大屏</Button>
      </Space>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={create} loading={loading}>新建退款申请</Button>
        <InputNumber value={amount} onChange={(v) => setAmount(v ?? 0)} min={0} addonBefore="金额" />
      </Space>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={cols}
        pagination={{ pageSize: 10 }}
        onRow={(r) => ({ onClick: () => nav(`/ticket/${r.id}`), style: { cursor: 'pointer' } })}
      />
    </div>
  )
}
