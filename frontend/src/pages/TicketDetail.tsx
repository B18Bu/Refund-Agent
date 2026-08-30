import { useEffect, useState } from 'react'
import { Card, Descriptions, Tag, Space, Button, Typography } from 'antd'
import { useParams, useNavigate } from 'react-router-dom'
import { Alert } from 'antd'
import { getSessionUser } from '../types/auth'
import client from '../api/client'
import FlowCanvas from '../components/FlowCanvas'
import ApprovePanel from '../components/ApprovePanel'

type Ticket = {
  id: number
  ticket_no: string
  amount: number
  status: string
  outcome: string
  error_code: string | null
  error_message: string | null
  fraud_score: number | null
  sentiment: string | null
  sentiment_text: string | null
  status_text: string
  outcome_text: string
  ocr_confidence: number | null
  ocr_text: string | null
  traces: { agent_name: string; status: string }[]
}

const statusColor: Record<string, string> = {
  RUNNING: 'blue',
  SUSPENDED: 'gold',
  COMPLETED: 'green',
}

// 舆情等级英文→中文兜底（后端已返回 sentiment_text，此处备用）
const sentimentCN: Record<string, string> = { LOW: '低', MEDIUM: '中', HIGH: '高' }

export default function TicketDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [t, setT] = useState<Ticket | null>(null)
  const [loadError, setLoadError] = useState(false)
  const user = getSessionUser()

  const load = () => client.get(`/tickets/${id}`)
    .then((r) => { setT(r.data); setLoadError(false) })
    .catch(() => setLoadError(true))

  useEffect(() => {
    load()
    // A-05：SSE 实时推送（收事件后重取详情），断线降级为 2s 轮询
    let poll: ReturnType<typeof setInterval> | null = null
    const es = new EventSource(`/api/tickets/${id}/events`)
    const refresh = () => { void load() }
    es.addEventListener('ticket_update', refresh)
    es.onerror = () => {
      // SSE 断线 → 启动 2s 轮询降级
      if (!poll) {
        poll = setInterval(() => {
          client.get(`/tickets/${id}`).then((r) => {
            setT(r.data)
            if (r.data.status === 'COMPLETED' && poll) {
              clearInterval(poll)
              poll = null
            }
          })
        }, 2000)
      }
    }
    return () => {
      es.close()
      es.removeEventListener('ticket_update', refresh)
      if (poll) clearInterval(poll)
    }
  }, [id])

  if (loadError) {
    return <Alert type="error" showIcon message="无权访问该工单或工单不存在" action={<Button size="small" onClick={() => nav(user?.role === 'sv' ? '/workspace' : '/my-tickets')}>返回列表</Button>} />
  }
  if (!t) return null

  return (
    <div className="ticket-detail">
      <Space className="ticket-detail-header" wrap>
        <Button onClick={() => nav(user?.role === 'sv' ? '/workspace' : '/my-tickets')}>← 返回</Button>
        <Typography.Title level={4} style={{ margin: 0 }}>工单 {t.ticket_no}</Typography.Title>
        <Tag color={statusColor[t.status]}>{t.status_text || t.status}</Tag>
        <Tag color={t.outcome === 'FAILED' ? 'volcano' : 'geekblue'}>{t.outcome_text || t.outcome}</Tag>
        {t.error_code && <Tag color="volcano">{t.error_code}</Tag>}
      </Space>

      <Descriptions bordered column={{ xs: 1, sm: 2, lg: 3 }}>
        <Descriptions.Item label="金额">¥{t.amount}</Descriptions.Item>
        <Descriptions.Item label="OCR 置信度">{t.ocr_confidence ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="欺诈分">{t.fraud_score ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="舆情等级">{t.sentiment_text ?? sentimentCN[t.sentiment ?? ''] ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="错误信息" span={2}>{t.error_message || '-'}</Descriptions.Item>
      </Descriptions>

      <Card title="OCR 识别结果" style={{ marginTop: 16 }}>
        <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{t.ocr_text || '（无识别结果）'}</pre>
      </Card>

      <Card title="Agent 决策流转" style={{ marginTop: 16 }}>
        <FlowCanvas traces={t.traces} />
      </Card>

      {t.status === 'SUSPENDED' && user?.role === 'sv' && (
        <Card title="人工审批" style={{ marginTop: 16 }}>
          <ApprovePanel ticketId={Number(id)} onDone={load} />
        </Card>
      )}
    </div>
  )
}
