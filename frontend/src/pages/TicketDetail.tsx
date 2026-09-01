import { useEffect, useState } from 'react'
import { Card, Descriptions, Tag, Space, Button, Typography, Steps } from 'antd'
import { useParams, useNavigate } from 'react-router-dom'
import { Alert } from 'antd'
import { getSessionUser } from '../types/auth'
import client from '../api/client'
import FlowCanvas from '../components/FlowCanvas'
import ApprovePanel from '../components/ApprovePanel'
import EvaluationDetail from '../components/EvaluationDetail'

type Ticket = {
  id: number
  ticket_no: string
  amount: number
  trace_id: string | null
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
  traces: { agent_name: string; status: string; output_summary: string | null }[]
  decision_reasons: string[] | null
  evidence_audit: {
    price_consistency: string
    order_authenticity: string
    goods_consistency: string
    security?: { risk: number; flags: string[] }
    action_policy?: { allowed: boolean; reason: string }
    intent?: { route: string; label: string; hit_rules: string[] }
    fallback?: { reasons: string[] }
  } | null
  management_suggestion: string | null
}

const statusColor: Record<string, string> = {
  RUNNING: 'blue',
  SUSPENDED: 'gold',
  COMPLETED: 'green',
}

// 舆情等级英文→中文兜底（后端已返回 sentiment_text，此处备用）
const sentimentCN: Record<string, string> = { LOW: '低', MEDIUM: '中', HIGH: '高' }

const REASON_CN: Record<string, string> = {
  amount_within_limit: '金额未超限',
  amount_over_limit: '金额超限',
  ocr_confidence_pass: 'OCR 置信度通过',
  ocr_confidence_below_threshold: 'OCR 置信度不足',
  ocr_amount_match: '价格一致',
  ocr_amount_mismatch: '价格不一致',
  ocr_amount_missing: '未识别到金额',
  fraud_pass: '欺诈分通过',
  fraud_score_at_threshold: '欺诈分偏高',
  sentiment_low: '舆情低',
  sentiment_not_low: '舆情非低',
  llm_call_failed: 'LLM 调用失败（已兜底）',
  llm_output_parse_fallback: 'LLM 输出解析失败（已兜底）',
}

const ACTION_POLICY_CN: Record<string, string> = {
  record_auto_refund_allowed: '允许记录自动退赔',
  payment_execution_not_supported: '不支持真实支付执行',
  tool_invocation_not_supported: '不支持工具调用',
  unregistered_action: '未登记动作',
  security_flags_present: '命中安全规则',
  security_risk_invalid: '安全风险值无效',
  security_risk_at_threshold: '安全风险触发阈值',
}

const INTENT_LABEL_CN: Record<string, string> = {
  refund_request: '退款申请',
  complaint: '投诉',
  malicious: '恶意/黑产',
  general: '一般咨询',
}

const INTENT_ROUTE_CN: Record<string, string> = {
  strong_signal: '强信号直判',
  llm_judge: 'LLM 判定',
}

const FLOW_STEP_INDEX: Record<string, number> = { RUNNING: 0, SUSPENDED: 1, COMPLETED: 2 }

const EVIDENCE_CN: Record<string, Record<string, { text: string; color: string }>> = {
  price_consistency: {
    match: { text: '一致', color: 'green' },
    mismatch: { text: '不一致', color: 'red' },
    missing: { text: '未识别到金额', color: 'orange' },
    unverified: { text: '未验证', color: 'default' },
  },
  order_authenticity: {
    pass: { text: '识别到订单号', color: 'green' },
    unverified: { text: '未识别到订单号', color: 'default' },
  },
  goods_consistency: {
    pass: { text: '含商品/凭证描述', color: 'green' },
    unverified: { text: '未识别到商品描述', color: 'default' },
  },
}

export default function TicketDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const [t, setT] = useState<Ticket | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [evaluationRefreshVersion, setEvaluationRefreshVersion] = useState(0)
  const user = getSessionUser()

  const load = () => client.get(`/tickets/${id}`)
    .then((r) => {
      setT(r.data)
      setLoadError(false)
      setEvaluationRefreshVersion((version) => version + 1)
    })
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
            setEvaluationRefreshVersion((version) => version + 1)
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

      <Card title="状态流转" size="small" style={{ marginTop: 16 }}>
        <Steps
          size="small"
          current={FLOW_STEP_INDEX[t.status] ?? 0}
          status={t.status === 'COMPLETED' ? 'finish' : 'process'}
          items={[
            { title: '运行中', description: 'Running' },
            { title: '挂起中', description: 'Suspended' },
            { title: '已完成', description: 'Completed' },
          ]}
        />
      </Card>

      <Card title="校验判断与管理建议" size="small" style={{ marginTop: 16 }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Descriptions bordered column={{ xs: 1, sm: 3 }} size="small">
            <Descriptions.Item label="价格一致性">
              <Tag color={EVIDENCE_CN.price_consistency[t.evidence_audit?.price_consistency ?? 'unverified']?.color}>
                {EVIDENCE_CN.price_consistency[t.evidence_audit?.price_consistency ?? 'unverified']?.text ?? '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="订单真实性">
              <Tag color={EVIDENCE_CN.order_authenticity[t.evidence_audit?.order_authenticity ?? 'unverified']?.color}>
                {EVIDENCE_CN.order_authenticity[t.evidence_audit?.order_authenticity ?? 'unverified']?.text ?? '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="商品一致性">
              <Tag color={EVIDENCE_CN.goods_consistency[t.evidence_audit?.goods_consistency ?? 'unverified']?.color}>
                {EVIDENCE_CN.goods_consistency[t.evidence_audit?.goods_consistency ?? 'unverified']?.text ?? '-'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="安全校验">
              {(t.evidence_audit?.security?.flags ?? []).length > 0 ? (
                <Tag color="red">
                  拦截：风险 {(t.evidence_audit?.security?.risk ?? 0).toFixed(2)}
                </Tag>
              ) : (
                <Tag color="green">通过</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="动作层策略">
              {t.evidence_audit?.action_policy ? (
                <Tag color={t.evidence_audit.action_policy.allowed ? 'green' : 'red'}>
                  {t.evidence_audit.action_policy.allowed ? '允许：' : '已拦截：'}
                  {ACTION_POLICY_CN[t.evidence_audit.action_policy.reason] ?? '未识别策略原因'}
                </Tag>
              ) : (
                <Tag color="default">未记录</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="意图分流">
              {t.evidence_audit?.intent?.route ? (
                <Tag color="blue">
                  {INTENT_ROUTE_CN[t.evidence_audit.intent.route] ?? t.evidence_audit.intent.route}：
                  {INTENT_LABEL_CN[t.evidence_audit.intent.label] ?? t.evidence_audit.intent.label}
                </Tag>
              ) : (
                <Tag color="default">未记录</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="异常兜底">
              {(t.evidence_audit?.fallback?.reasons ?? []).length > 0 ? (
                <Space wrap>
                  {(t.evidence_audit?.fallback?.reasons ?? []).map((reason) => (
                    <Tag key={reason} color="volcano">
                      {REASON_CN[reason] ?? reason}
                    </Tag>
                  ))}
                </Space>
              ) : (
                <Tag color="green">无</Tag>
              )}
            </Descriptions.Item>
          </Descriptions>
          <Space wrap>
            {(t.decision_reasons ?? []).map((reason) => (
              <Tag key={reason} color={reason.includes('pass') || reason.includes('low') ? 'green' : 'orange'}>
                {REASON_CN[reason] ?? reason}
              </Tag>
            ))}
          </Space>
          <Alert
            type={t.status === 'COMPLETED' && t.outcome === 'AUTO_REFUNDED' ? 'success' : 'warning'}
            showIcon
            message="管理建议"
            description={t.management_suggestion || '系统未给出建议，请人工复核。'}
          />
        </Space>
      </Card>

      <Descriptions bordered column={{ xs: 1, sm: 2, lg: 3 }}>
        <Descriptions.Item label="金额">¥{t.amount}</Descriptions.Item>
        <Descriptions.Item label="OCR 置信度">{t.ocr_confidence ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="欺诈分">{t.fraud_score ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="舆情等级">{t.sentiment_text ?? sentimentCN[t.sentiment ?? ''] ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="触发原因">
          {t.traces.find((tr) => tr.agent_name === 'Decision')?.output_summary || '-'}
        </Descriptions.Item>
        <Descriptions.Item label="Trace ID" span={2}>{t.trace_id || '-'}</Descriptions.Item>
        <Descriptions.Item label="错误信息" span={2}>{t.error_message || '-'}</Descriptions.Item>
      </Descriptions>

      <Card title="OCR 识别结果" style={{ marginTop: 16 }}>
        <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{t.ocr_text || '（无识别结果）'}</pre>
      </Card>

      <Card title="Agent 决策流转" style={{ marginTop: 16 }}>
        <FlowCanvas traces={t.traces} />
      </Card>

      {user?.role === 'sv' && (
        <EvaluationDetail ticketId={Number(id)} refreshVersion={evaluationRefreshVersion} />
      )}

      {t.status === 'SUSPENDED' && user?.role === 'sv' && (
        <Card title="人工审批" style={{ marginTop: 16 }}>
          <ApprovePanel ticketId={Number(id)} onDone={load} />
        </Card>
      )}
    </div>
  )
}
