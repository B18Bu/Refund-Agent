import { useCallback, useEffect, useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { Alert, Button, Card, Descriptions, Empty, Skeleton, Statistic, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import client from '../api/client'
import type { SecurityEvent, SecurityGovernanceSummary } from '../types/securityGovernance'

const { Paragraph, Text, Title } = Typography

const formatPercent = (value: number | undefined) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
const formatTime = (value: string | undefined) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '未记录生成时间'

function ReportValue({ available, value }: { available: boolean; value: string | number }) {
  return available ? <>{value}</> : <Text type="secondary">报告暂不可用</Text>
}

export default function SecurityGovernance() {
  const [summary, setSummary] = useState<SecurityGovernanceSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const { data } = await client.get<SecurityGovernanceSummary>('/security-governance/summary')
      setSummary(data)
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

  const attackCategories = summary?.red_blue.available ? summary.red_blue.categories ?? [] : []
  const attackChart = useMemo(() => ({
    aria: { enabled: true, description: '最近一次红蓝测试各攻击类型的样本数与拦截率' },
    tooltip: { trigger: 'axis' },
    legend: { data: ['样本数', '拦截率'] },
    xAxis: { type: 'category', data: attackCategories.map((item) => item.category), axisLabel: { rotate: 25 } },
    yAxis: [
      { type: 'value', name: '样本数', minInterval: 1 },
      { type: 'value', name: '拦截率', min: 0, max: 1, axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%` } },
    ],
    series: [
      { name: '样本数', type: 'bar', data: attackCategories.map((item) => item.sample_count), itemStyle: { color: '#1677ff' } },
      { name: '拦截率', type: 'bar', yAxisIndex: 1, data: attackCategories.map((item) => item.block_rate), itemStyle: { color: '#52c41a' } },
    ],
  }), [attackCategories])

  const eventColumns: TableColumnsType<SecurityEvent> = [
    { title: '工单', dataIndex: 'ticket_ref', render: (value: string) => value },
    { title: '风险值', dataIndex: 'risk', render: (value: number) => value.toFixed(2) },
    { title: '规则标签', dataIndex: 'flags', render: (flags: string[]) => flags.map((flag) => <Tag key={flag}>{flag}</Tag>) },
    { title: '处置', dataIndex: 'outcome', render: (value: string) => <Tag color={value === 'PENDING' ? 'warning' : 'blue'}>{value}</Tag> },
  ]

  if (loading) return <Skeleton active paragraph={{ rows: 12 }} />
  if (error) return <Alert type="error" showIcon message="安全治理数据加载失败" description="安全规则、审批和退赔流程不受此页面影响，请稍后重试。" action={<Button onClick={load}>重新加载</Button>} />
  if (!summary) return <Card><Empty description="安全治理数据暂不可用" /></Card>

  const gapColor: Record<string, string> = { complete: 'success', partial: 'processing', pending: 'warning' }
  const auditCounts = summary.audit.available ? Object.entries(summary.audit.finding_counts ?? {}) : []

  return (
    <main className="security-governance-page">
      <header className="page-header">
        <div>
          <Title level={2}>安全治理中心</Title>
          <Paragraph type="secondary">集中查看结构化安全证据与脱敏运行事件；此页面只读，不改变既有审批或退赔裁决。</Paragraph>
        </div>
        <Button onClick={load}>重新加载</Button>
      </header>

      <section className="security-governance-kpis" aria-label="安全治理核心指标">
        <Card><Statistic title="待人工复核" value={summary.runtime.pending_human_review} /><Text type="secondary">最近 50 条工单聚合</Text></Card>
        <Card><Statistic title="攻击拦截率" valueRender={() => <ReportValue available={summary.red_blue.available} value={formatPercent(summary.red_blue.block_rate)} />} /><Text type="secondary">最近一次红蓝测试</Text></Card>
        <Card><Statistic title="DLP 准确率" valueRender={() => <ReportValue available={summary.dlp.available} value={formatPercent(summary.dlp.accuracy)} />} /><Text type="secondary">本地验证集质量门禁</Text></Card>
        <Card><Statistic title="安全审计" valueRender={() => <ReportValue available={summary.audit.available} value={summary.audit.status ?? '—'} />} /><Text type="secondary">静态安全审计结果</Text></Card>
      </section>

      <section className="security-governance-grid">
        <Card title="最近一次红蓝测试" className="security-governance-card">
          {summary.red_blue.available ? (
            <>
              <Descriptions size="small" column={2} className="security-governance-description">
                <Descriptions.Item label="生成时间">{formatTime(summary.red_blue.generated_at)}</Descriptions.Item>
                <Descriptions.Item label="攻击样本">{summary.red_blue.attack_count ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="合法对照">{summary.red_blue.legitimate_count ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="误拦截率">{formatPercent(summary.red_blue.false_positive_block_rate)}</Descriptions.Item>
              </Descriptions>
              {attackCategories.length > 0 ? <figure aria-label="攻击类型样本数和拦截率柱状图">
                <ReactECharts option={attackChart} style={{ height: 300 }} />
                <figcaption><strong>攻击类型数值明细：</strong>{attackCategories.map((item) => `${item.category}：${item.sample_count} 条，拦截 ${formatPercent(item.block_rate)}`).join('；')}。</figcaption>
              </figure> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无攻击类型统计" />}
            </>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="报告暂不可用" />}
        </Card>

        <Card title="当前治理缺口" className="security-governance-card">
          <div className="security-governance-gaps">
            {summary.gaps.map((gap) => <article key={gap.key} className="security-governance-gap">
              <div><Text strong>{gap.title}</Text><Paragraph type="secondary">{gap.description}</Paragraph></div>
              <Tag color={gapColor[gap.status] ?? 'default'}>{gap.status === 'partial' ? '部分覆盖' : gap.status === 'complete' ? '已覆盖' : '待补足'}</Tag>
            </article>)}
          </div>
        </Card>
      </section>

      <section className="security-governance-grid">
        <Card title="审计与 DLP 报告" className="security-governance-card">
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="DLP 验收"><ReportValue available={summary.dlp.available} value={summary.dlp.acceptance_status ?? '—'} /></Descriptions.Item>
            <Descriptions.Item label="DLP 样本"><ReportValue available={summary.dlp.available} value={summary.dlp.sample_count ?? '—'} /></Descriptions.Item>
            <Descriptions.Item label="审计发现"><ReportValue available={summary.audit.available} value={auditCounts.map(([key, value]) => `${key}: ${value}`).join('；') || '—'} /></Descriptions.Item>
          </Descriptions>
        </Card>
        <Card title="数据口径" className="security-governance-card">
          <Paragraph>运行事件仅来自最近 50 条工单的风险值、规则标签和处置结果，不展示 OCR、攻击原文、图片、令牌或密钥。</Paragraph>
          <Paragraph>红蓝、DLP 和审计数据来自本地结构化报告；缺失或无法解析时显示“报告暂不可用”，不会以零值替代。</Paragraph>
          <Text type="secondary">页面聚合时间：{formatTime(summary.generated_at)}</Text>
        </Card>
      </section>

      <Card title="脱敏运行事件" className="security-governance-table">
        {summary.runtime.recent_events.length > 0 ? <Table<SecurityEvent> rowKey={(event) => `${event.ticket_ref}-${event.created_at ?? ''}`} columns={eventColumns} dataSource={summary.runtime.recent_events} pagination={false} scroll={{ x: 720 }} /> : <Empty description="暂无命中安全规则的运行事件" />}
      </Card>
    </main>
  )
}
