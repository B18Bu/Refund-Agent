import { CloseOutlined, CustomerServiceOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons'
import { Button, Input, Spin } from 'antd'
import { FormEvent, useEffect, useState } from 'react'
import client from '../api/client'
import type { CustomerSupportConversation, CustomerSupportReply } from '../types/shop'

type Message = { sender: 'CUSTOMER' | 'ASSISTANT' | 'SYSTEM'; content: string; evidence?: CustomerSupportReply['evidence'] }

const suggestions = ['推荐一款适合拍照的手机', '查询我的订单状态', '售后保修规则是什么？']

export default function CustomerAssistant() {
  const [open, setOpen] = useState(false)
  const [conversation, setConversation] = useState<CustomerSupportConversation>()
  const [messages, setMessages] = useState<Message[]>([])
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)

  const reset = () => { setConversation(undefined); setMessages([]); setMessage(''); setFailed(false) }

  useEffect(() => {
    if (!open) return
    const closeOnEscape = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [open])

  const send = (event?: FormEvent<HTMLFormElement>, preset?: string) => {
    event?.preventDefault()
    const question = (preset || message).trim()
    if (!question || loading) return
    setLoading(true); setFailed(false)
    const start = conversation ? Promise.resolve({ data: conversation }) : client.post<CustomerSupportConversation>('/customer-assistant/conversations')
    start.then(({ data }) => {
      setConversation(data)
      return client.post<CustomerSupportReply>(`/customer-assistant/conversations/${data.id}/messages`, { message: question, context: {} })
    }).then(({ data }) => {
      setMessages((current) => [...current, { sender: 'CUSTOMER', content: question }, { sender: 'ASSISTANT', content: data.answer, evidence: data.evidence }])
      setMessage('')
    }).catch(() => setFailed(true)).finally(() => setLoading(false))
  }
  const escalate = () => conversation && client.post(`/customer-assistant/conversations/${conversation.id}/escalations`).then(() => setMessages((current) => [...current, { sender: 'SYSTEM', content: '已转人工客服处理，你可以继续查看本次对话记录。' }])).catch(() => setFailed(true))

  return <div className="assistant-widget">
    <button type="button" className="assistant-launcher" onClick={() => setOpen(true)} aria-label="打开智能客服" title="智能客服"><CustomerServiceOutlined aria-hidden="true" /></button>
    {open && <section className="assistant-float" role="dialog" aria-label="智能客服对话" aria-labelledby="customer-assistant-title">
      <header className="assistant-chat__header"><div><h2 id="customer-assistant-title">智能客服</h2><span><i />在线</span></div><div className="assistant-chat__actions"><Button type="text" icon={<PlusOutlined />} onClick={reset} aria-label="开始新对话" title="开始新对话" /><Button type="text" icon={<CloseOutlined />} onClick={() => setOpen(false)} aria-label="关闭智能客服" title="关闭智能客服" /></div></header>
      <div className="assistant-messages" aria-live="polite">
        {!messages.length && <article className="assistant-message assistant-message--assistant assistant-message--greeting"><span className="assistant-message__sender">智能客服</span><div className="assistant-message__bubble"><p>你好，我是你的智能客服。今天想咨询商品、订单还是售后？</p><div className="assistant-message__suggestions">{suggestions.map((item) => <button key={item} type="button" onClick={() => send(undefined, item)}>{item}</button>)}</div></div></article>}
        {messages.map((item, index) => <article key={index} className={`assistant-message assistant-message--${item.sender.toLowerCase()}`}><span className="assistant-message__sender">{item.sender === 'CUSTOMER' ? '你' : item.sender === 'ASSISTANT' ? '智能客服' : '系统'}</span><div className="assistant-message__bubble"><p>{item.content}</p>{item.evidence?.sources?.length ? <div className="assistant-message__sources">{item.evidence.sources.map((source) => <a key={source} href={source} target="_blank" rel="noreferrer">查看商品资料</a>)}</div> : null}</div></article>)}
        {loading && <div className="assistant-typing"><Spin size="small" />智能客服正在整理资料...</div>}
      </div>
      {failed && <p className="assistant-error" role="alert">服务暂时不可用，请重试或转人工处理。</p>}
      <form className="assistant-composer" onSubmit={send}><Input.TextArea aria-label="输入消息" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="输入你的问题，例如：帮我比较上一款和这款的夜拍表现" autoSize={{ minRows: 1, maxRows: 5 }} maxLength={2000} /><Button htmlType="submit" type="primary" icon={<SendOutlined />} aria-label="发送消息" disabled={!message.trim()} loading={loading}>发送</Button></form>
      {conversation && <button type="button" className="assistant-escalate" onClick={escalate}>需要人工处理？转人工客服</button>}
    </section>}
  </div>
}
