import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import CustomerSupportChat from './CustomerSupportChat'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

function serviceToken() {
  return `x.${btoa(JSON.stringify({ sub: '7', role: 'cs' })).replace(/=/g, '')}.x`
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise })
  return { promise, resolve }
}

describe('CustomerSupportChat', () => {
  afterEach(() => { cleanup(); localStorage.clear(); vi.clearAllMocks(); vi.useRealTimers() })

  it('领取人工会话并发送客服回复', async () => {
    localStorage.setItem('token', serviceToken())
    vi.mocked(client.get).mockImplementation((url) => Promise.resolve({
      data: url === '/customer-support/cases'
        ? [{ id: 3, conversation_id: 9, status: 'OPEN', summary_masked: '用户咨询订单', assigned_to: null }]
        : [{ id: 10, sender: 'CUSTOMER', content: '订单什么时候发货？', evidence: {}, created_at: '2026-09-09T12:00:00Z' }],
    } as never))
    vi.mocked(client.post)
      .mockResolvedValueOnce({ data: { id: 3, status: 'IN_PROGRESS', assigned_to: 7 } } as never)
      .mockResolvedValueOnce({ data: { id: 11, sender: 'AGENT', content: '我来帮你查询', evidence: {}, created_at: '2026-09-09T12:01:00Z' } } as never)

    render(<CustomerSupportChat />)

    expect(await screen.findByRole('button', { name: /用户咨询订单/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '领取会话' }))
    expect(await screen.findByText('订单什么时候发货？')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: '客服回复' }), { target: { value: '我来帮你查询' } })
    fireEvent.click(screen.getByRole('button', { name: '发送回复' }))

    expect(await screen.findByText('我来帮你查询')).toBeInTheDocument()
    expect(client.post).toHaveBeenCalledWith('/customer-support/cases/3/messages', { content: '我来帮你查询' })
  })

  it('未领取或由其他客服领取的会话不能发送回复', async () => {
    localStorage.setItem('token', serviceToken())
    vi.mocked(client.get).mockImplementation((url) => Promise.resolve({
      data: url === '/customer-support/cases'
        ? [{ id: 4, conversation_id: 10, status: 'IN_PROGRESS', summary_masked: '其他客服处理中', assigned_to: 8 }]
        : [],
    } as never))

    render(<CustomerSupportChat />)

    expect(await screen.findByRole('button', { name: /其他客服处理中/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '发送回复' })).toBeDisabled()
  })

  it('每两秒同时刷新会话列表和当前会话消息', async () => {
    vi.useFakeTimers()
    localStorage.setItem('token', serviceToken())
    vi.mocked(client.get).mockImplementation((url) => Promise.resolve({
      data: url === '/customer-support/cases'
        ? [{ id: 3, conversation_id: 9, status: 'IN_PROGRESS', summary_masked: '用户咨询订单', assigned_to: 7 }]
        : [],
    } as never))

    render(<CustomerSupportChat />)
    await vi.advanceTimersByTimeAsync(2000)

    expect(client.get).toHaveBeenCalledWith('/customer-support/cases')
    expect(client.get).toHaveBeenCalledWith('/customer-support/cases/3/messages')
    expect(vi.mocked(client.get).mock.calls.filter(([url]) => url === '/customer-support/cases')).toHaveLength(2)
  })

  it('切换会话后忽略较晚返回的旧会话消息', async () => {
    localStorage.setItem('token', serviceToken())
    const firstMessages = deferred<{ data: unknown }>()
    const secondMessages = deferred<{ data: unknown }>()
    vi.mocked(client.get).mockImplementation((url) => {
      if (url === '/customer-support/cases') return Promise.resolve({ data: [
        { id: 3, conversation_id: 9, status: 'OPEN', summary_masked: '第一个会话', assigned_to: null },
        { id: 4, conversation_id: 10, status: 'OPEN', summary_masked: '第二个会话', assigned_to: null },
      ] } as never)
      return url === '/customer-support/cases/3/messages' ? firstMessages.promise as never : secondMessages.promise as never
    })

    render(<CustomerSupportChat />)
    await screen.findByRole('button', { name: /第一个会话/ })
    fireEvent.click(screen.getByRole('button', { name: /第二个会话/ }))

    await act(async () => { secondMessages.resolve({ data: [{ id: 20, sender: 'CUSTOMER', content: '第二个会话消息', evidence: {}, created_at: null }] }) })
    expect(await screen.findByText('第二个会话消息')).toBeInTheDocument()
    await act(async () => { firstMessages.resolve({ data: [{ id: 10, sender: 'CUSTOMER', content: '第一个会话消息', evidence: {}, created_at: null }] }) })

    expect(screen.queryByText('第一个会话消息')).not.toBeInTheDocument()
  })

  it('在会话列表中显示最近更新时间', async () => {
    localStorage.setItem('token', serviceToken())
    vi.mocked(client.get).mockImplementation((url) => Promise.resolve({
      data: url === '/customer-support/cases'
        ? [{ id: 3, conversation_id: 9, status: 'OPEN', summary_masked: '用户咨询订单', assigned_to: null, updated_at: '2026-09-10T12:34:00Z' }]
        : [],
    } as never))

    render(<CustomerSupportChat />)

    expect(await screen.findByText('更新时间：2026-09-10 12:34')).toBeInTheDocument()
  })
})
