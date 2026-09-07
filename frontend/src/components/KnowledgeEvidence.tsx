import { useEffect, useState } from 'react'
import { Alert, Card, Empty, Skeleton, Space, Tag, Typography } from 'antd'
import client from '../api/client'

type Evidence = {
  content: string
  source: string
  section: string | null
  version: string
  similarity: number
}

type KnowledgeResponse = {
  available: boolean
  status: 'ok' | 'empty' | 'unavailable'
  results: Evidence[]
}

type Props = {
  endpoint: string
  title?: string
}

export default function KnowledgeEvidence({ endpoint, title = '政策依据' }: Props) {
  const [response, setResponse] = useState<KnowledgeResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    client.get<KnowledgeResponse>(endpoint)
      .then(({ data }) => { if (active) setResponse(data) })
      .catch(() => { if (active) setResponse({ available: false, status: 'unavailable', results: [] }) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [endpoint])

  if (loading) return <Card title={title} className="knowledge-evidence"><Skeleton active paragraph={{ rows: 3 }} /></Card>
  if (!response || response.status === 'unavailable') {
    return <Card title={title} className="knowledge-evidence"><Alert type="warning" showIcon message="政策依据暂不可用" description="不影响现有工单处理。" /></Card>
  }
  if (response.status === 'empty') {
    return <Card title={title} className="knowledge-evidence"><Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未检索到匹配的政策原文" /></Card>
  }

  return (
    <Card title={title} className="knowledge-evidence">
      <Space direction="vertical" size="middle" style={{ width: '100%' }} aria-live="polite">
        {response.results.map((item, index) => (
          <article className="knowledge-evidence__item" key={`${item.source}-${item.section ?? ''}-${index}`}>
            <Space wrap size={[6, 6]}>
              <Tag color="blue">来源：{item.source}</Tag>
              <Tag>章节：{item.section || '未标注'}</Tag>
              <Tag>版本：{item.version}</Tag>
              <Tag color="green">相似度：{item.similarity.toFixed(3)}</Tag>
            </Space>
            <Typography.Paragraph className="knowledge-evidence__content">{item.content}</Typography.Paragraph>
          </article>
        ))}
      </Space>
    </Card>
  )
}
