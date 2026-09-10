import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Empty, Input, List, Space, Tag, Typography } from 'antd'
import client from '../api/client'
import { getSessionUser } from '../types/auth'
import type { CustomerSupportCase, CustomerSupportMessage } from '../types/shop'

const statusLabel: Record<CustomerSupportCase['status'], string> = { OPEN: '待领取', IN_PROGRESS: '处理中', RESOLVED: '已结束' }

export default function CustomerSupportChat() {
  const user = getSessionUser()
  const [cases, setCases] = useState<CustomerSupportCase[]>([])
  const [selectedId, setSelectedId] = useState<number>()
  const [messages, setMessages] = useState<CustomerSupportMessage[]>([])
  const [content, setContent] = useState('')
  const [error, setError] = useState('')
  const selectedIdRef = useRef<number>()
  const selected = useMemo(() => cases.find((item) => item.id === selectedId), [cases, selectedId])
  const canReply = selected?.status === 'IN_PROGRESS' && String(selected.assigned_to) === user?.id

  useEffect(() => { selectedIdRef.current = selectedId }, [selectedId])

  const loadCases = useCallback(async () => {
    try {
      const { data } = await client.get<CustomerSupportCase[]>('/customer-support/cases')
      setCases(data)
      setSelectedId((current) => current && data.some((item) => item.id === current) ? current : data[0]?.id)
    } catch { setError('会话列表暂时无法加载') }
  }, [])
  const loadMessages = useCallback(async (caseId: number) => {
    try {
      const { data } = await client.get<CustomerSupportMessage[]>(`/customer-support/cases/${caseId}/messages`)
      if (selectedIdRef.current !== caseId) return
      setMessages((current) => {
        const known = new Set(current.map((item) => item.id))
        const incoming = data.filter((item) => !known.has(item.id))
        return incoming.length ? [...current, ...incoming] : current
      })
    } catch { setError('会话消息暂时无法加载') }
  }, [])

  useEffect(() => { void loadCases() }, [loadCases])
  useEffect(() => { setMessages([]); if (selectedId) void loadMessages(selectedId) }, [loadMessages, selectedId])
  useEffect(() => {
    if (!selectedId || selected?.status === 'RESOLVED') return
    const timer = window.setInterval(() => { void loadCases(); void loadMessages(selectedId) }, 2000)
    return () => window.clearInterval(timer)
  }, [loadCases, loadMessages, selected?.status, selectedId])

  const assign = async () => {
    if (!selected) return
    try {
      const { data } = await client.post<CustomerSupportCase>(`/customer-support/cases/${selected.id}/assign`)
      setCases((current) => current.map((item) => item.id === selected.id ? { ...item, status: 'IN_PROGRESS', assigned_to: data.assigned_to } : item))
      await loadMessages(selected.id)
    } catch { setError('领取会话未成功，请刷新后重试') }
  }
  const resolve = async () => {
    if (!selected || !canReply) return
    try {
      await client.post(`/customer-support/cases/${selected.id}/resolve`)
      setCases((current) => current.map((item) => item.id === selected.id ? { ...item, status: 'RESOLVED' } : item))
    } catch { setError('结束会话未成功，请刷新后重试') }
  }
  const send = async () => {
    const text = content.trim()
    if (!selected || !canReply || !text) return
    try {
      const { data } = await client.post<CustomerSupportMessage>(`/customer-support/cases/${selected.id}/messages`, { content: text })
      setMessages((current) => current.some((item) => item.id === data.id) ? current : [...current, data])
      setContent('')
    } catch { setError('发送回复未成功，请刷新后重试') }
  }

  return <section className="support-chat page-wrap">
    <div className="page-header"><div><Typography.Title level={2}>人工答疑</Typography.Title><Typography.Text type="secondary">领取用户转人工的会话并提供答复。</Typography.Text></div><Button onClick={() => void loadCases()}>刷新会话</Button></div>
    {error && <Alert type="error" showIcon message="操作失败" description={error} closable onClose={() => setError('')} />}
    <div className="support-chat__workspace">
      <aside className="support-chat__cases" aria-label="人工会话列表"><List dataSource={cases} locale={{ emptyText: <Empty description="暂无待处理会话" /> }} renderItem={(item) => <List.Item className={item.id === selectedId ? 'is-selected' : ''} onClick={() => setSelectedId(item.id)}><button type="button"><Space direction="vertical" size={2}><Typography.Text strong>{item.summary_masked || '用户请求人工协助'}</Typography.Text><Space><Tag>{statusLabel[item.status]}</Tag><Typography.Text type="secondary">会话 #{item.conversation_id}</Typography.Text></Space>{item.updated_at && <Typography.Text type="secondary">更新时间：{item.updated_at.slice(0, 16).replace('T', ' ')}</Typography.Text>}</Space></button></List.Item>} /></aside>
      <main className="support-chat__thread">{selected ? <><header><div><Typography.Title level={4}>{selected.summary_masked || '用户请求人工协助'}</Typography.Title><Typography.Text type="secondary">{canReply ? '你正在处理此会话' : selected.status === 'OPEN' ? '领取后可回复用户' : selected.status === 'RESOLVED' ? '会话已结束' : '该会话由其他客服处理'}</Typography.Text></div><Space>{selected.status === 'OPEN' && <Button type="primary" onClick={() => void assign()}>领取会话</Button>}{canReply && <Button onClick={() => void resolve()}>结束会话</Button>}</Space></header><div className="support-chat__messages" aria-live="polite">{messages.map((item) => <article key={item.id} className={`support-chat__message support-chat__message--${item.sender.toLowerCase()}`}><span>{item.sender === 'CUSTOMER' ? '用户' : item.sender === 'AGENT' ? '人工客服' : '系统'}</span><p>{item.content}</p></article>)}</div><div className="support-chat__composer"><Input.TextArea aria-label="客服回复" value={content} onChange={(event) => setContent(event.target.value)} disabled={!canReply} maxLength={2000} placeholder={canReply ? '输入回复内容' : '仅领取该会话的客服可回复'} /><Button type="primary" disabled={!canReply || !content.trim()} onClick={() => void send()}>发送回复</Button></div></> : <Empty description="请选择一个会话" />}</main>
    </div>
  </section>
}
