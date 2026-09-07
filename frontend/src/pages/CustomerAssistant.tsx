import { Button, Input, Spin } from 'antd'
import { FormEvent, useState } from 'react'
import client from '../api/client'
import type { CustomerAssistantReply } from '../types/shop'

export default function CustomerAssistant() {
  const [message, setMessage] = useState('')
  const [reply, setReply] = useState<CustomerAssistantReply>()
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)

  const send = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const question = message.trim()
    if (!question) return
    setLoading(true)
    setFailed(false)
    client.post<CustomerAssistantReply>('/customer-assistant/reply', { message: question, context: {} })
      .then((response) => setReply(response.data))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false))
  }

  return <main className="page-wrap customer-assistant" aria-labelledby="customer-assistant-title">
    <section className="customer-assistant__intro">
      <p className="shop-eyebrow">官方商品资料咨询</p>
      <h1 id="customer-assistant-title">商品咨询助手</h1>
      <p>根据商城已收录的商品资料回答问题，并展示可核验的来源。</p>
    </section>
    <form className="customer-assistant__form" onSubmit={send}>
      <Input.TextArea aria-label="咨询商品" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="例如：推荐一款适合拍照的手机" autoSize={{ minRows: 3, maxRows: 6 }} maxLength={2000} />
      <Button htmlType="submit" type="primary" loading={loading} disabled={!message.trim()}>发送咨询</Button>
    </form>
    {loading && <div className="customer-assistant__status" aria-live="polite"><Spin size="small" />正在检索商品资料</div>}
    {failed && <p className="customer-assistant__error" role="alert">咨询暂时不可用，请稍后重试。</p>}
    {reply && <section className="customer-assistant__reply" aria-label="咨询回复">
      <h2>回复</h2>
      <p>{reply.answer}</p>
      {reply.sources.length ? <section className="customer-assistant__sources" aria-labelledby="customer-assistant-sources">
        <h3 id="customer-assistant-sources">推荐依据</h3>
        <ul>{reply.sources.map((source) => <li key={`${source.source_url}-${source.crawled_at || ''}`}>
          <a href={source.source_url} target="_blank" rel="noreferrer" aria-label="查看商品资料来源">商品资料来源</a>
          <span>抓取时间：{source.crawled_at || '未提供'}</span>
        </li>)}</ul>
      </section> : <p className="customer-assistant__fallback">当前回答没有可展示的商品资料来源，请以商城商品详情为准。</p>}
    </section>}
  </main>
}
