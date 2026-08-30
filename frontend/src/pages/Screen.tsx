import { useEffect, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { Button, Space } from 'antd'
import { useNavigate } from 'react-router-dom'
import client from '../api/client'

type Row = {
  id: number
  ticket_no: string
  amount: number
  status: string
  outcome: string
  fraud_score: number | null
  sentiment: string | null
  created_at: string | null
}

function countBy(rows: Row[], key: 'status' | 'outcome'): Record<string, number> {
  const m: Record<string, number> = {}
  for (const r of rows) m[r[key]] = (m[r[key]] ?? 0) + 1
  return m
}

const statusCN: Record<string, string> = {
  RUNNING: '处理中',
  SUSPENDED: '待人工审批',
  COMPLETED: '已完成',
}
const outcomeCN: Record<string, string> = {
  PENDING: '待定',
  AUTO_REFUNDED: '自动退赔',
  APPROVED: '已批准',
  REJECTED: '已拒绝',
  FAILED: '处理失败',
}

export default function Screen() {
  const [rows, setRows] = useState<Row[]>([])
  const nav = useNavigate()

  const load = () => client.get('/tickets').then((r) => setRows(r.data))
  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  const status = countBy(rows, 'status')
  const outcome = countBy(rows, 'outcome')
  const avgFraud = rows.length ? rows.reduce((s, r) => s + (r.fraud_score ?? 0), 0) / rows.length : 0
  const totalAmount = rows.reduce((s, r) => s + r.amount, 0)
  const pending = rows.filter((r) => r.status === 'SUSPENDED').length

  const barOption = {
    tooltip: {},
    xAxis: { type: 'category', data: Object.keys(status).map((s) => statusCN[s] ?? s) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: Object.values(status), itemStyle: { color: '#5470c6' } }],
  }
  const pieOption = {
    tooltip: {},
    series: [
      {
        type: 'pie',
        radius: ['40%', '65%'],
        data: Object.entries(outcome).map(([name, value]) => ({ name: outcomeCN[name] ?? name, value })),
      },
    ],
  }

  const box: React.CSSProperties = {
    background: 'rgba(0,21,41,0.9)',
    color: '#fff',
    padding: 20,
    borderRadius: 8,
    textAlign: 'center',
  }

  return (
    <div className="screen-page">
      <Space className="screen-header" wrap>
        <h2>客诉舆情退赔决策 · 实时大屏</h2>
        <Button onClick={() => nav('/')}>返回工作台</Button>
      </Space>
      <div className="screen-stats">
        <div style={box}><div style={{ fontSize: 32 }}>{rows.length}</div><div>工单总数</div></div>
        <div style={box}><div style={{ fontSize: 32 }}>{pending}</div><div>待人工审批</div></div>
        <div style={box}><div style={{ fontSize: 32 }}>{avgFraud.toFixed(1)}</div><div>平均欺诈分</div></div>
        <div style={box}><div style={{ fontSize: 32 }}>¥{totalAmount.toFixed(2)}</div><div>申请总金额</div></div>
      </div>
      <div className="screen-charts">
        <div className="screen-chart">
          <ReactECharts option={barOption} style={{ height: 320 }} />
        </div>
        <div className="screen-chart">
          <ReactECharts option={pieOption} style={{ height: 320 }} />
        </div>
      </div>
    </div>
  )
}
