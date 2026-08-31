import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, Empty, Progress, Skeleton, Tag, Typography } from 'antd'
import client from '../api/client'
import type { EvaluationRecord, MeasurementType } from '../types/evaluation'

const { Text } = Typography
type EvaluationResponse = {
  available: boolean
  status: string
  record?: EvaluationRecord
}

const sourceLabels: Record<MeasurementType, string> = {
  actual: '真实 usage',
  estimated: '离线估算',
  mixed: '混合口径',
}
const number = (value: number | null) => value == null ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const ratio = (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const tokenChange = (value: number | null) => value == null ? '—' : value < 0 ? `增加 ${number(Math.abs(value))}` : value > 0 ? `减少 ${number(value)}` : '持平 0'
const ratioChange = (value: number | null) => value == null ? '—' : value < 0 ? `增幅 ${ratio(Math.abs(value))}` : value > 0 ? `降幅 ${ratio(value)}` : '持平 0%'

export default function EvaluationDetail({ ticketId, refreshVersion }: { ticketId: number; refreshVersion: number }) {
  const [data, setData] = useState<EvaluationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const response = await client.get<EvaluationResponse>(`/tickets/${ticketId}/evaluation`)
      setData(response.data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [ticketId, refreshVersion])

  useEffect(() => { void load() }, [load])

  if (loading) return <Card className="evaluation-detail" title="评测与成本"><Skeleton active paragraph={{ rows: 4 }} /></Card>
  if (error) {
    return <Card className="evaluation-detail" title="评测与成本"><Alert type="warning" showIcon message="评测暂不可用" description="工单处理和人工审批不受影响。" action={<Button size="small" onClick={load}>重试</Button>} /></Card>
  }
  if (!data?.available || !data.record) {
    return <Card className="evaluation-detail" title="评测与成本"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评测数据" /></Card>
  }

  const record = data.record
  const scores = [
    ['正确性', record.correctness_score],
    ['安全性', record.safety_score],
    ['解释完整性', record.explainability_score],
  ] as const
  const latencyEntries = Object.entries(record.latency_breakdown)

  return (
    <Card
      className="evaluation-detail"
      title="评测与成本"
      extra={<Tag>{sourceLabels[record.measurement_type]}</Tag>}
    >
      <Descriptions className="evaluation-detail__metrics" bordered column={{ xs: 1, sm: 2, lg: 4 }}>
        <Descriptions.Item label="基线输入 Token">{number(record.baseline_input_tokens)}</Descriptions.Item>
        <Descriptions.Item label="当前输入 Token">{number(record.current_input_tokens)}</Descriptions.Item>
        <Descriptions.Item label="输出 Token">{number(record.current_output_tokens)}</Descriptions.Item>
        <Descriptions.Item label="当前总 Token">{number(record.current_total_tokens)}</Descriptions.Item>
        <Descriptions.Item label="Token 变化">
          <Text type={record.saved_tokens != null && record.saved_tokens < 0 ? 'danger' : undefined}>{tokenChange(record.saved_tokens)}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="比例变化">
          <Text type={record.reduction_ratio != null && record.reduction_ratio < 0 ? 'danger' : undefined}>{ratioChange(record.reduction_ratio)}</Text>
        </Descriptions.Item>
        <Descriptions.Item label="Prompt 版本">{record.prompt_version}</Descriptions.Item>
        <Descriptions.Item label="模型来源">{record.provider}</Descriptions.Item>
      </Descriptions>

      <div className="evaluation-detail__grid">
        <section aria-labelledby="evaluation-score-title">
          <h3 id="evaluation-score-title">三维评分</h3>
          {scores.map(([label, value]) => (
            <div key={label} className="evaluation-detail__score">
              <Text>{label}</Text>
              <Progress percent={value == null ? 0 : value / 2 * 100} format={() => value == null ? '待评测' : `${value.toFixed(1)} / 2`} />
            </div>
          ))}
          <Text type="secondary">依据：{record.reason_summary || '暂无脱敏原因摘要'}</Text>
        </section>

        <section aria-labelledby="evaluation-latency-title">
          <h3 id="evaluation-latency-title">阶段耗时</h3>
          {latencyEntries.length ? (
            <dl className="evaluation-latency-list">
              {latencyEntries.map(([stage, milliseconds]) => (
                <div key={stage}><dt>{stage}</dt><dd>{milliseconds.toFixed(2)} ms</dd></div>
              ))}
            </dl>
          ) : <Text type="secondary">暂无阶段耗时数据</Text>}
          <Text type="secondary">决策路径：{record.decision_route || '待定'}</Text>
        </section>
      </div>
    </Card>
  )
}
