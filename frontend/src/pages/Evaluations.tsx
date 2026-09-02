import { useCallback, useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { Alert, Button, Card, Empty, Progress, Skeleton, Statistic, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { useNavigate } from 'react-router-dom'
import client from '../api/client'
import type { EvaluationRecord, EvaluationSummary, MeasurementType, OrchestrationSnapshot } from '../types/evaluation'

const { Paragraph, Text, Title } = Typography
const sourceLabels: Record<MeasurementType, string> = {
  actual: '真实 usage',
  estimated: '离线估算',
  mixed: '混合口径',
}

const formatNumber = (value: number | null) => value == null ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: 1 })
const formatRatio = (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const tokenChange = (value: number | null) => value == null ? '—' : value < 0 ? `增加 ${formatNumber(Math.abs(value))}` : value > 0 ? `减少 ${formatNumber(value)}` : '持平 0'
const ratioChange = (value: number | null) => value == null ? '—' : value < 0 ? `增幅 ${formatRatio(Math.abs(value))}` : value > 0 ? `降幅 ${formatRatio(value)}` : '持平 0%'

export default function Evaluations() {
  const [summary, setSummary] = useState<EvaluationSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [orchestration, setOrchestration] = useState<OrchestrationSnapshot | null>(null)
  const navigate = useNavigate()

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await client.get<EvaluationSummary>('/evaluations/summary')
      setSummary(data)
      const orchestrationResponse = await client.get<OrchestrationSnapshot>('/evaluations/orchestration')
      setOrchestration(orchestrationResponse.data)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    window.addEventListener('refund-refresh', load)
    return () => window.removeEventListener('refund-refresh', load)
  }, [load])

  const comparisonOption = useMemo(() => ({
    aria: { enabled: true, description: '旧版基线与当前版本平均输入 Token 对比' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['旧版基线', '当前版本'] },
    xAxis: { type: 'category', data: ['平均输入 Token'] },
    yAxis: { type: 'value', name: 'Token' },
    series: [
      { name: '旧版基线', type: 'bar', data: [summary?.avg_baseline_input_tokens ?? 0], itemStyle: { color: '#64748b' }, label: { show: true, position: 'top' } },
      { name: '当前版本', type: 'bar', data: [summary?.avg_current_input_tokens ?? 0], itemStyle: { color: '#1677ff' }, label: { show: true, position: 'top' } },
    ],
  }), [summary])

  const trendOption = useMemo(() => ({
    aria: { enabled: true, description: '近 7 日旧版基线与当前版本 Token 变化趋势' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['旧版基线', '当前版本'] },
    xAxis: { type: 'category', data: summary?.trend.map((point) => point.date) ?? [] },
    yAxis: { type: 'value', name: 'Token' },
    series: [
      { name: '旧版基线', type: 'line', lineStyle: { type: 'dashed', color: '#64748b' }, itemStyle: { color: '#64748b' }, data: summary?.trend.map((point) => point.baseline_input_tokens) ?? [] },
      { name: '当前版本', type: 'line', lineStyle: { type: 'solid', color: '#1677ff' }, itemStyle: { color: '#1677ff' }, data: summary?.trend.map((point) => point.current_input_tokens) ?? [] },
    ],
  }), [summary])

  const columns: TableColumnsType<EvaluationRecord> = [
    { title: '工单', dataIndex: 'ticket_id', render: (value) => `#${value}` },
    { title: '状态', dataIndex: 'evaluation_status', render: (value) => <Tag color={value === 'PASSED' ? 'success' : 'warning'}>{value}</Tag> },
    { title: '当前 Token', dataIndex: 'current_total_tokens', render: formatNumber },
    { title: 'Token 变化', dataIndex: 'saved_tokens', render: (value) => <Text type={value != null && value < 0 ? 'danger' : undefined}>{tokenChange(value)}</Text> },
    { title: '比例变化', dataIndex: 'reduction_ratio', render: (value) => <Text type={value != null && value < 0 ? 'danger' : undefined}>{ratioChange(value)}</Text> },
    { title: '来源', dataIndex: 'measurement_type', render: (value: MeasurementType) => sourceLabels[value] },
  ]

  if (loading) return <Skeleton active paragraph={{ rows: 10 }} />
  if (error) return <Alert type="error" showIcon message="评测数据加载失败" description="审批与退赔流程不受影响，请稍后重试。" action={<Button onClick={load}>重新加载</Button>} />
  if (!summary) return <Card><Empty description="暂无评测数据" /></Card>

  const hasEvaluations = summary.evaluation_count > 0
  const sourceSummary = summary.measurement_types.map((type) => sourceLabels[type]).join(' / ') || '暂无真实工单数据'
  const goldenValue = summary.golden.passed
    ? `通过 ${summary.golden.case_count ?? 0}/${summary.golden.case_count ?? 0}`
    : `未通过 · 得分 ${summary.golden.score ?? 0}/${summary.golden.max_score ?? 0}`

  const scoreItems = [
    ['正确性', summary.average_scores.correctness],
    ['安全性', summary.average_scores.safety],
    ['解释完整性', summary.average_scores.explainability],
  ] as const

  return (
    <main className="evaluation-page">
      <header className="page-header">
        <div>
          <Title level={2}>Agent 评测中心</Title>
          <Paragraph type="secondary">查看确定性评分、Token 优化幅度和执行趋势。评测异常不会改变审批结果。</Paragraph>
        </div>
        <div className="evaluation-sources" aria-label="数据来源">
          {summary.measurement_types.map((type) => <Tag key={type}>{sourceLabels[type]}</Tag>)}
        </div>
      </header>

      {orchestration && <section className="orchestration-panel" aria-label="工单 8 编排评测">
        <Card title="编排评测中心" extra={<Tag color="blue">工单 8</Tag>}>
          <Paragraph type="secondary">展示从输入到决策的节点链路、意图分流效率和异常兜底状态。</Paragraph>
          <div className="orchestration-pipeline" aria-label="编排节点链路">
            {orchestration.pipeline.map((node, index) => <span key={node.key} className="orchestration-node"><strong>{node.label}</strong>{index < orchestration.pipeline.length - 1 && <i aria-hidden="true">→</i>}</span>)}
          </div>
          <div className="orchestration-kpis">
            <Statistic title="意图样本" value={orchestration.intent.sample_count} suffix="条" />
            <Statistic title="强信号跳过 LLM" value={orchestration.intent.strong_signal} suffix="条" />
            <Statistic title="LLM 分流" value={orchestration.intent.llm_judge} suffix="条" />
            <Statistic title="Token 降低" value={orchestration.ab.token_reduction == null ? '—' : formatRatio(orchestration.ab.token_reduction)} />
          </div>
          <div className="orchestration-footer"><Text>Fallback：{orchestration.fallback.reasons.map((reason) => <Tag key={reason}>{reason}</Tag>)}</Text><Text type="secondary">审计状态：{orchestration.fallback.audited ? '已覆盖' : '待覆盖'}</Text></div>
        </Card>
      </section>}

      {hasEvaluations ? (
        <>
          <section className="evaluation-kpis" aria-label="Token 核心指标">
            <Card><Statistic title="当前平均 Token" value={formatNumber(summary.avg_current_input_tokens)} /><Text type="secondary">口径：{sourceSummary}</Text></Card>
            <Card><Statistic title="旧版平均基线" value={formatNumber(summary.avg_baseline_input_tokens)} /><Text type="secondary">口径：离线估算</Text></Card>
            <Card><Statistic title="平均 Token 变化" value={tokenChange(summary.avg_saved_tokens)} /><Text type="secondary">口径：{sourceSummary}</Text></Card>
            <Card><Statistic title="平均比例变化" value={ratioChange(summary.avg_reduction_ratio)} /><Text type="secondary">口径：{sourceSummary}</Text></Card>
          </section>

          <section className="evaluation-chart-grid">
            <Card title="Token 前后对比" className="evaluation-card">
              <figure aria-label="Token 前后对比柱状图">
                <ReactECharts option={comparisonOption} style={{ height: 280 }} />
                <figcaption><strong>Token 数值明细：</strong>旧版 {formatNumber(summary.avg_baseline_input_tokens)}，当前 {formatNumber(summary.avg_current_input_tokens)}，{tokenChange(summary.avg_saved_tokens)}（{ratioChange(summary.avg_reduction_ratio)}）。</figcaption>
              </figure>
            </Card>
            <Card title="近 7 日趋势" className="evaluation-card">
              <figure aria-label="近 7 日 Token 趋势图">
                <ReactECharts option={trendOption} style={{ height: 280 }} />
                <figcaption>
                  <strong>近 7 日数值：</strong>
                  <ul className="evaluation-data-list">
                    {summary.trend.map((point) => <li key={point.date}>{point.date}：基线 {formatNumber(point.baseline_input_tokens)}，当前 {formatNumber(point.current_input_tokens)}，样本 {point.count}</li>)}
                  </ul>
                </figcaption>
              </figure>
            </Card>
          </section>
        </>
      ) : (
        <Card><Empty description="暂无评测数据" /><Paragraph type="secondary">新工单完成首次 START 决策后将在此展示；Golden 规则回归仍可独立查看。</Paragraph></Card>
      )}

      <section className="evaluation-secondary-grid">
        {hasEvaluations && <Card title="三维平均评分">
          <div className="evaluation-scores">
            {scoreItems.map(([label, value]) => (
              <div key={label}>
                <Text>{label}</Text>
                <Progress percent={value == null ? 0 : value / 2 * 100} format={() => value == null ? '待评测' : `${value.toFixed(1)} / 2`} />
              </div>
            ))}
          </div>
          <Text type="secondary">评分完整度：{summary.data_completeness.score_records}/{summary.evaluation_count}</Text>
        </Card>}
        <Card title="Golden Dataset">
          {summary.golden.available ? (
            <Statistic title="规则回归" value={goldenValue} />
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Golden 报告暂不可用" />}
        </Card>
      </section>

      {hasEvaluations && <Card title="最近评测记录" className="evaluation-table-card">
        <Table<EvaluationRecord>
          rowKey="id"
          columns={columns}
          dataSource={summary.recent}
          pagination={false}
          scroll={{ x: 760 }}
          onRow={(record) => ({
            className: 'evaluation-row',
            tabIndex: 0,
            onClick: () => navigate(`/ticket/${record.ticket_id}`),
            onKeyDown: (event) => {
              if (event.key === 'Enter') navigate(`/ticket/${record.ticket_id}`)
            },
          })}
        />
      </Card>}
    </main>
  )
}
