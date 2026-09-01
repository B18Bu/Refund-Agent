import { Button, Card, Steps, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import { StatusLegend } from '../components/StatusLegend'

const steps = [
  { title: '提交申请', description: '客服填写退款金额并上传订单或商品凭证。' },
  { title: '凭证 OCR', description: '系统识别凭证文字，置信度不足时会转人工审核。' },
  { title: '安全校验', description: '对凭证做 PII 脱敏与注入/越狱检测，命中高风险强制人工复核。' },
  { title: '意图识别', description: '规则层先过滤强信号（黑产/刷单等），未命中才交给 LLM 做风险与舆情判定。' },
  { title: '异常兜底', description: 'LLM 解析失败或调用异常时显式记录原因并保守兜底，绝不静默自动放行。' },
  { title: '金额决策', description: '系统综合金额、凭证、风险与舆情生成处理建议。' },
  { title: '处理结果', description: '符合规则时自动退赔；其余订单交主管审批；异常会标记为处理失败。' },
]

export default function ProcessOverview() {
  const nav = useNavigate()
  return (
    <div>
      <Typography.Title level={3}>退款流程总览</Typography.Title>
      <Typography.Paragraph type="secondary">本页解释系统的标准处理链路，不展示单个订单的实时进度。</Typography.Paragraph>
      <Card>
        <Steps direction="vertical" items={steps} />
      </Card>
      <Card title="结果状态说明" style={{ marginTop: 16 }}>
        <StatusLegend />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          自动退赔表示已按规则完成；待人工审批需要主管决定；处理失败表示流程出现异常，需要优先排查。
        </Typography.Paragraph>
      </Card>
      <Button style={{ marginTop: 16 }} onClick={() => nav('/workspace')}>返回退款工作台</Button>
    </div>
  )
}
