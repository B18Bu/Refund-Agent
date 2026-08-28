import { Tag } from 'antd'

const statusColor: Record<string, string> = {
  RUNNING: 'blue',
  SUSPENDED: 'orange',
  COMPLETED: 'green',
}

const outcomeColor: Record<string, string> = {
  PENDING: 'default',
  AUTO_REFUNDED: 'cyan',
  APPROVED: 'green',
  REJECTED: 'red',
  FAILED: 'error',
}

const statusText: Record<string, string> = {
  RUNNING: '处理中',
  SUSPENDED: '待人工审批',
  COMPLETED: '已完成',
}

const outcomeText: Record<string, string> = {
  PENDING: '待定',
  AUTO_REFUNDED: '自动退赔',
  APPROVED: '已批准',
  REJECTED: '已拒绝',
  FAILED: '处理失败',
}

export function StatusTag({ status, text }: { status: string; text?: string | null }) {
  return <Tag color={statusColor[status]}>{text || statusText[status] || status}</Tag>
}

export function OutcomeTag({ outcome, text }: { outcome: string; text?: string | null }) {
  return <Tag color={outcomeColor[outcome]}>{text || outcomeText[outcome] || outcome}</Tag>
}

export function StatusLegend() {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <StatusTag status="RUNNING" />
      <StatusTag status="SUSPENDED" />
      <OutcomeTag outcome="FAILED" />
      <StatusTag status="COMPLETED" />
    </div>
  )
}
