import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Empty, List, Space, Tag, Typography, message } from 'antd'
import client from '../api/client'

type ManualReturn = {
  id: number
  ticket_id: number
  return_no: string
  reason: string
  description?: string
  status: string
  amount: number
  product_name?: string
  decision_reasons: string[]
  evidence_paths: string[]
}

export default function ServiceRefunds() {
  const [rows, setRows] = useState<ManualReturn[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [approving, setApproving] = useState<number>()

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await client.get<ManualReturn[]>('/tickets/service/returns')
      setRows(data)
    } catch (requestError: any) {
      setError(requestError.response?.data?.detail || '退款队列暂时无法加载')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const refresh = () => void load()
    window.addEventListener('refund-refresh', refresh)
    return () => window.removeEventListener('refund-refresh', refresh)
  }, [load])

  const approve = async (ticketId: number, action: 'APPROVE' | 'REJECT') => {
    setApproving(ticketId)
    try {
      await client.post(`/tickets/${ticketId}/approve`, { action, comment: '退款凭证已人工复核' })
      message.success(action === 'APPROVE' ? '已批准退款申请' : '已驳回退款申请')
      await load()
    } catch (requestError: any) {
      message.error(requestError.response?.data?.detail || '审批未完成，请刷新队列')
      await load()
    } finally {
      setApproving(undefined)
    }
  }

  return <section className="service-refunds page-wrap">
    <div className="page-header"><div><Typography.Title level={2}>退款审核队列</Typography.Title><Typography.Text type="secondary">仅显示待人工处理的退单；提交审批后将由决策流继续处理。</Typography.Text></div><Button onClick={() => void load()} loading={loading}>刷新队列</Button></div>
    {error && <Alert type="error" showIcon message="加载失败" description={error} action={<Button size="small" onClick={() => void load()}>重试</Button>} />}
    <Card className="service-refunds__card">
      <List loading={loading} dataSource={rows} locale={{ emptyText: <Empty description="当前没有待审核退款" /> }} renderItem={(row) => <List.Item className="service-refunds__item">
        <div className="service-refunds__info"><Space wrap><Typography.Text strong>{row.return_no}</Typography.Text><Tag color="orange">待人工审核</Tag><Typography.Text type="danger">¥{row.amount.toFixed(2)}</Typography.Text></Space><Typography.Paragraph>{row.product_name || '商品信息待同步'} · {row.reason}</Typography.Paragraph>{row.description && <Typography.Paragraph type="secondary">问题说明：{row.description}</Typography.Paragraph>}<Typography.Text type="secondary">审计凭证：</Typography.Text><Space wrap>{row.evidence_paths.length ? row.evidence_paths.map((path) => <Typography.Text code key={path}>{path}</Typography.Text>) : <Typography.Text type="warning">未上传凭证，已强制人工审核</Typography.Text>}</Space>{row.decision_reasons.length > 0 && <Typography.Paragraph type="secondary">转人工原因：{row.decision_reasons.join('、')}</Typography.Paragraph>}</div>
        <Space className="service-refunds__actions"><Button danger loading={approving === row.ticket_id} disabled={approving !== undefined} onClick={() => void approve(row.ticket_id, 'REJECT')}>驳回</Button><Button type="primary" loading={approving === row.ticket_id} disabled={approving !== undefined} onClick={() => void approve(row.ticket_id, 'APPROVE')}>批准退款</Button></Space>
      </List.Item>} />
    </Card>
  </section>
}
