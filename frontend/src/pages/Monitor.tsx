import { useCallback, useEffect, useRef, useState } from 'react'
import { Alert, Button, Card, Empty, List, Space, Statistic, Typography, message } from 'antd'
import { ExclamationCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import client from '../api/client'
import { OutcomeTag, StatusTag } from '../components/StatusLegend'

type Row = {
  id: number
  ticket_no: string
  amount: number
  status: string
  status_text: string
  outcome: string
  outcome_text: string
  error_code: string | null
  created_at: string | null
}

export default function Monitor() {
  const nav = useNavigate()
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const previousPriorityIds = useRef<Set<number> | null>(null)

  const load = useCallback(async (notify = true) => {
    try {
      const { data } = await client.get<Row[]>('/tickets')
      const nextPriorityIds = new Set(data.filter((row) => row.outcome === 'FAILED' || row.status === 'SUSPENDED').map((row) => row.id))
      if (notify && previousPriorityIds.current) {
        const additions = [...nextPriorityIds].filter((id) => !previousPriorityIds.current?.has(id))
        const failed = data.filter((row) => additions.includes(row.id) && row.outcome === 'FAILED').length
        const pending = additions.length - failed
        if (failed) message.error(`新增 ${failed} 个处理异常订单`)
        if (pending) message.warning(`新增 ${pending} 个待人工审批订单`)
      }
      previousPriorityIds.current = nextPriorityIds
      setRows(data)
      setUpdatedAt(new Date())
      setError(false)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(false)
    const timer = window.setInterval(() => load(), 5000)
    const refresh = () => load(false)
    window.addEventListener('refund-refresh', refresh)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('refund-refresh', refresh)
    }
  }, [load])

  const failed = rows.filter((row) => row.outcome === 'FAILED')
  const pending = rows.filter((row) => row.status === 'SUSPENDED')
  const running = rows.filter((row) => row.status === 'RUNNING')
  const priorityRows = [...failed, ...pending]
  const totalAmount = rows.reduce((total, row) => total + row.amount, 0)

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 20 }} wrap>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>实时监控</Typography.Title>
          <Typography.Text type={error ? 'danger' : 'secondary'}>
            {error ? '数据加载失败，可重试' : `自动刷新中 · 最近更新：${updatedAt ? updatedAt.toLocaleTimeString() : '加载中'}`}
          </Typography.Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => load(false)} loading={loading}>立即刷新</Button>
      </Space>
      {error && <Alert type="error" showIcon message="无法加载退款订单" description="请检查网络或服务状态后重试。" style={{ marginBottom: 16 }} />}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 16 }}>
        <Card><Statistic title="异常订单" value={failed.length} valueStyle={{ color: '#cf1322' }} prefix={<ExclamationCircleOutlined />} /></Card>
        <Card><Statistic title="待人工审批" value={pending.length} valueStyle={{ color: '#d48806' }} /></Card>
        <Card><Statistic title="正在处理" value={running.length} valueStyle={{ color: '#1677ff' }} /></Card>
        <Card><Statistic title="当前申请金额" value={totalAmount} precision={2} prefix="¥" valueStyle={{ color: '#389e0d' }} /></Card>
      </div>

      <Card title="需要优先处理" style={{ marginTop: 16 }}>
        {priorityRows.length ? (
          <List
            dataSource={priorityRows}
            renderItem={(row) => (
              <List.Item actions={[<Button key="detail" type="link" onClick={() => nav(`/ticket/${row.id}`)}>{row.status === 'SUSPENDED' ? '去审批' : '查看详情'}</Button>]}>
                <List.Item.Meta
                  title={<Space><Typography.Text strong>{row.ticket_no}</Typography.Text>{row.outcome === 'FAILED' ? <OutcomeTag outcome={row.outcome} text={row.outcome_text} /> : <StatusTag status={row.status} text={row.status_text} />}</Space>}
                  description={row.outcome === 'FAILED' ? (row.error_code || '处理失败，请查看详情') : `申请金额 ¥${row.amount.toFixed(2)}`}
                />
              </List.Item>
            )}
          />
        ) : <Empty description="当前没有需要立即处理的订单" />}
      </Card>

      <Card title="当前处理状态概览" style={{ marginTop: 16 }}>
        <Space size="large" wrap>
          <span>正在处理：<b>{running.length}</b></span>
          <span>等待人工审批：<b>{pending.length}</b></span>
          <span>已完成：<b>{rows.filter((row) => row.status === 'COMPLETED').length}</b></span>
          <span>处理失败：<b>{failed.length}</b></span>
        </Space>
      </Card>
    </div>
  )
}
