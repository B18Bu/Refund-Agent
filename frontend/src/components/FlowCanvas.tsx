import ReactECharts from 'echarts-for-react'

type Trace = {
  agent_name: string
  status: string
}

const STATUS_COLOR: Record<string, string> = {
  PENDING: '#d9d9d9',
  RUNNING: '#1890ff',
  SUCCESS: '#52c41a',
  SUSPENDED: '#faad14',
  FAILED: '#f5222d',
}

const STATUS_CN: Record<string, string> = {
  PENDING: '待处理',
  RUNNING: '处理中',
  SUCCESS: '成功',
  SUSPENDED: '挂起待审',
  FAILED: '失败',
}

// 固定节点顺序（与后端 agent_traces 命名一致）+ 中文展示名
const NODE_ORDER: { key: string; label: string }[] = [
  { key: 'Intake', label: '录入' },
  { key: 'OCR', label: '凭证识别' },
  { key: 'Fraud', label: '风控' },
  { key: 'Sentiment', label: '舆情' },
  { key: 'Decision', label: '决策' },
  { key: 'HumanReview', label: '人工审批' },
]

function nodeColor(status: string | undefined): string {
  return STATUS_COLOR[status ?? 'PENDING'] ?? STATUS_COLOR.PENDING
}

function nodeStatusCN(status: string | undefined): string {
  return STATUS_CN[status ?? 'PENDING'] ?? status ?? '待处理'
}

export default function FlowCanvas({ traces }: { traces: Trace[] }) {
  const statusMap: Record<string, string> = {}
  for (const t of traces) statusMap[t.agent_name] = t.status

  const nodes = NODE_ORDER.map((n, i) => ({
    name: n.key,
    x: i * 200,
    y: 0,
    itemStyle: { color: nodeColor(statusMap[n.key]) },
    symbolSize: 60,
    label: {
      show: true,
      position: 'bottom',
      fontSize: 12,
      formatter: () => `${n.label}\n${nodeStatusCN(statusMap[n.key])}`,
    },
  }))
  const links = nodes.slice(0, -1).map((n, i) => ({ source: n.name, target: nodes[i + 1].name }))

  const option = {
    tooltip: {
      formatter: (p: any) => {
        const st = statusMap[p.data.name] ?? 'PENDING'
        return `${p.data.name}<br/>状态：${nodeStatusCN(st)}`
      },
    },
    series: [
      {
        type: 'graph',
        layout: 'none',
        data: nodes,
        links,
        roam: true,
        lineStyle: { color: '#8c8c8c', width: 2 },
      },
    ],
  }
  return <ReactECharts option={option} style={{ height: 320 }} />
}
