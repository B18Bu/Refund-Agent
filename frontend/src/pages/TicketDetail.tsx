import { useEffect, useState } from 'react'
import { Card, Descriptions, Tag, Space, Button, Typography } from 'antd'
import { useParams, useNavigate } from 'react-router-dom'
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
  ocr_confidence: number | null
  ocr_text: string | null
  traces: { agent_name: string; status: string }[]
}

const statusColor: Record<string, string> = {
  RUNNING: 'blue',
  SUSPENDED: 'gold',
  COMPLETED: 'green',
}

export default function TicketDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [t, setT] = useState<Ticket | null>(null)

  const load = () => client.get(`/tickets/${id}`).then((r) => setT(r.data))

  useEffect(() => {
    load()
    // A-05：SSE 实时推送（收事件后重取详情），断线降级为 2s 轮询
    let poll: ReturnType<typeof setInterval> | null = null
    const es = new EventSource(`/api/tickets/${id}/events`)
    es.onmessage = () => {
      load()
    }
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
      if (poll) clearInterval(poll)
    }
  }, [id])

  if (!t) return null

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => nav('/')}>← 返回</Button>
        <Typography.Title level={4} style={{ margin: 0 }}>工单 {t.ticket_no}</Typography.Title>
        <Tag color={statusColor[t.status]}>{t.status}</Tag>
        <Tag color={t.outcome === 'FAILED' ? 'volcano' : 'geekblue'}>{t.outcome}</Tag>
        {t.error_code && <Tag color="volcano">{t.error_code}</Tag>}
      </Space>

      <Descriptions bordered column={3}>
        <Descriptions.Item label="金额">¥{t.amount}</Descriptions.Item>
        <Descriptions.Item label="OCR 置信度">{t.ocr_confidence ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="欺诈分">{t.fraud_score ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="舆情等级">{t.sentiment ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="错误信息" span={2}>{t.error_message || '-'}</Descriptions.Item>
      </Descriptions>

      <Card title="OCR 识别结果" style={{ marginTop: 16 }}>
        <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{t.ocr_text || '（无识别结果）'}</pre>
      </Card>

      <Card title="Agent 决策流转" style={{ marginTop: 16 }}>
        <FlowCanvas traces={t.traces} />
      </Card>

      {t.status === 'SUSPENDED' && (
        <Card title="人工审批" style={{ marginTop: 16 }}>
          <ApprovePanel ticketId={Number(id)} onDone={load} />
        </Card>
      )}
    </div>
  )
}
