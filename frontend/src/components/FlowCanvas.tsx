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

// 固定节点顺序（与后端 agent_traces 命名一致）
const NODE_ORDER = ['Intake', 'OCR', 'Fraud', 'Sentiment', 'Decision', 'HumanReview']

function nodeColor(status: string | undefined): string {
  return STATUS_COLOR[status ?? 'PENDING'] ?? STATUS_COLOR.PENDING
}

export default function FlowCanvas({ traces }: { traces: Trace[] }) {
  const statusMap: Record<string, string> = {}
  for (const t of traces) statusMap[t.agent_name] = t.status

  const nodes = NODE_ORDER.map((name, i) => ({
    name,
    x: i * 200,
    y: 0,
    itemStyle: { color: nodeColor(statusMap[name]) },
    symbolSize: 60,
  }))
  const links = nodes.slice(0, -1).map((n, i) => ({ source: n.name, target: nodes[i + 1].name }))

  const option = {
    tooltip: { show: true },
    series: [
      {
        type: 'graph',
        layout: 'none',
        data: nodes,
        links,
        roam: true,
        label: { show: true, position: 'bottom', fontSize: 12 },
        lineStyle: { color: '#8c8c8c', width: 2 },
      },
    ],
  }
  return <ReactECharts option={option} style={{ height: 320 }} />
}
