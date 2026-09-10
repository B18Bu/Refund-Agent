import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import CustomerAssistant from './CustomerAssistant'

const seededMessages = vi.hoisted(() => ({ value: undefined as unknown }))

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react')
  return {
    ...actual,
    useState: <T,>(initial: T) => actual.useState(Array.isArray(initial) && initial.length === 0 && seededMessages.value !== undefined ? seededMessages.value as T : initial),
  }
})

describe('CustomerAssistant', () => {
  afterEach(() => { cleanup(); seededMessages.value = undefined; vi.useRealTimers(); vi.restoreAllMocks() })

  it('keeps the conversation hidden until the floating customer-service button opens it', () => {
    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)

    expect(screen.getByRole('button', { name: '打开智能客服' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: '智能客服' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))

    expect(screen.getByRole('dialog', { name: '智能客服' })).toBeInTheDocument()
    expect(screen.getByText('你好，我是你的智能客服。今天想咨询商品、订单还是售后？')).toBeInTheDocument()
  })

  it('preserves both message roles in the floating conversation', async () => {
    vi.mocked(client.post)
      .mockResolvedValueOnce({ data: { id: 9, status: 'OPEN' } } as never)
      .mockResolvedValueOnce({ data: { conversation_id: 9, answer: '可以帮你比较夜拍表现。', intent: 'CATALOG', evidence: {} } } as never)

    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))
    fireEvent.change(screen.getByRole('textbox', { name: '输入消息' }), { target: { value: '推荐拍照手机' } })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByText('推荐拍照手机')).toBeInTheDocument()
    expect(screen.getByText('可以帮你比较夜拍表现。')).toBeInTheDocument()
  })

  it('先展示推荐商品名称和说明，再提供商品详情入口', async () => {
    vi.mocked(client.post)
      .mockResolvedValueOnce({ data: { id: 9, status: 'OPEN' } } as never)
      .mockResolvedValueOnce({ data: {
        conversation_id: 9,
        answer: '推荐这款旗舰影像手机。',
        intent: 'CATALOG',
        evidence: { products: [{ product_id: 7, product_name: '影像旗舰 X7', description: '夜拍表现更出色', image_url: 'https://example.com/products/7.jpg', source_url: 'https://example.com/products/7' }, { product_id: 8, product_name: '备用 X8', source_url: 'https://example.com/products/8' }, { product_id: 0, source_url: 'https://example.com/invalid' }] },
      } } as never)

    render(<MemoryRouter initialEntries={['/shop']}><Routes><Route path="*" element={<CustomerAssistant />} /><Route path="/shop/products/7" element={<p>商品 7 详情页</p>} /><Route path="/shop/products/8" element={<p>商品 8 详情页</p>} /></Routes></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))
    fireEvent.change(screen.getByRole('textbox', { name: '输入消息' }), { target: { value: '推荐拍照手机' } })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

    const productButtons = await screen.findAllByRole('button', { name: '查看商品信息' })
    expect(productButtons).toHaveLength(1)
    expect(screen.getByText('推荐这款旗舰影像手机。')).toBeInTheDocument()
    expect(screen.getByText('影像旗舰 X7')).toBeInTheDocument()
    expect(screen.getByText('夜拍表现更出色')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '影像旗舰 X7' })).toHaveAttribute('src', 'https://example.com/products/7.jpg')
    expect(screen.queryByRole('link', { name: '查看商品资料' })).not.toBeInTheDocument()

    fireEvent.click(productButtons[0])

    expect(await screen.findByText('商品 7 详情页')).toBeInTheDocument()
    expect(screen.queryByText('商品 8 详情页')).not.toBeInTheDocument()
  })

  it('keeps customer and system messages as text when products evidence is attached', () => {
    seededMessages.value = [
      { sender: 'CUSTOMER', content: '客户消息', evidence: { products: [{ product_id: 7, source_url: 'https://example.com/products/7' }] } },
      { sender: 'SYSTEM', content: '系统消息', evidence: { products: [{ product_id: 8, source_url: 'https://example.com/products/8' }] } },
    ]

    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))

    expect(screen.getByText('客户消息')).toBeInTheDocument()
    expect(screen.getByText('系统消息')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查看商品信息' })).not.toBeInTheDocument()
  })

  it('keeps the assistant text when every referenced product ID is invalid', async () => {
    vi.mocked(client.post)
      .mockResolvedValueOnce({ data: { id: 9, status: 'OPEN' } } as never)
      .mockResolvedValueOnce({ data: {
        conversation_id: 9,
        answer: '暂时没有可跳转的商品。',
        intent: 'CATALOG',
        evidence: { products: [{ product_id: 0, source_url: 'https://example.com/zero' }, { product_id: -1, source_url: 'https://example.com/negative' }, { product_id: 7.5, source_url: 'https://example.com/fraction' }] },
      } } as never)

    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))
    fireEvent.change(screen.getByRole('textbox', { name: '输入消息' }), { target: { value: '推荐拍照手机' } })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByText('暂时没有可跳转的商品。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查看商品信息' })).not.toBeInTheDocument()
  })

  it('默认收起历史会话，并可加载已结束会话为只读消息', async () => {
    vi.mocked(client.get).mockImplementation((url) => Promise.resolve({ data: url === '/customer-assistant/conversations'
      ? [{ id: 6, status: 'RESOLVED', summary_masked: '上次咨询夜拍' }]
      : { status: 'RESOLVED', messages: [{ id: 20, sender: 'CUSTOMER', content: '历史问题', evidence: {}, created_at: null }] },
    } as never))
    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))
    expect(screen.queryByLabelText('历史会话列表')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '历史会话' }))
    fireEvent.click(await screen.findByRole('button', { name: /上次咨询夜拍/ }))
    expect(await screen.findByText('历史问题')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '输入消息' })).toBeDisabled()
  })

  it('转人工后轮询并展示客服回复', async () => {
    vi.mocked(client.post)
      .mockResolvedValueOnce({ data: { id: 9, status: 'OPEN' } } as never)
      .mockResolvedValueOnce({ data: { conversation_id: 9, answer: '正在为你转接人工客服。', intent: 'OTHER', evidence: {} } } as never)
      .mockResolvedValueOnce({ data: { case_id: 3, status: 'OPEN' } } as never)
    vi.mocked(client.get).mockResolvedValue({ data: {
      status: 'OPEN',
      messages: [
        { id: 10, sender: 'CUSTOMER', content: '需要人工帮助', evidence: {}, created_at: '2026-09-09T11:59:00Z' },
        { id: 11, sender: 'ASSISTANT', content: '正在为你转接人工客服。', evidence: {}, created_at: '2026-09-09T12:00:00Z' },
        { id: 12, sender: 'AGENT', content: '您好，我来协助处理', evidence: {}, created_at: '2026-09-09T12:00:01Z' },
      ],
    } } as never)

    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))
    fireEvent.change(screen.getByRole('textbox', { name: '输入消息' }), { target: { value: '需要人工帮助' } })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))
    await screen.findByText('正在为你转接人工客服。')

    fireEvent.click(screen.getByRole('button', { name: '需要人工处理？转人工客服' }))

    expect(await screen.findByText('您好，我来协助处理')).toBeInTheDocument()
    expect(screen.getByText('人工客服')).toBeInTheDocument()
    expect(screen.getAllByText('需要人工帮助')).toHaveLength(1)
    expect(screen.getAllByText('正在为你转接人工客服。')).toHaveLength(1)
    expect(screen.getAllByText('智能客服')).toHaveLength(2)
    expect(client.get).toHaveBeenCalledWith('/customer-assistant/conversations/9/messages')
  })

  it('人工服务结束后显示提示并停止两秒轮询', async () => {
    const clearIntervalSpy = vi.spyOn(window, 'clearInterval')
    vi.mocked(client.post)
      .mockResolvedValueOnce({ data: { id: 9, status: 'OPEN' } } as never)
      .mockResolvedValueOnce({ data: { conversation_id: 9, answer: '正在为你转接人工客服。', intent: 'OTHER', evidence: {} } } as never)
      .mockResolvedValueOnce({ data: { case_id: 3, status: 'OPEN' } } as never)
    vi.mocked(client.get).mockResolvedValue({ data: {
      status: 'RESOLVED',
      messages: [{ id: 12, sender: 'AGENT', content: '问题已处理完成', evidence: {}, created_at: '2026-09-09T12:00:01Z' }],
    } } as never)

    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))
    fireEvent.change(screen.getByRole('textbox', { name: '输入消息' }), { target: { value: '需要人工帮助' } })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))
    await screen.findByText('正在为你转接人工客服。')
    fireEvent.click(screen.getByRole('button', { name: '需要人工处理？转人工客服' }))

    await screen.findByText('本次人工服务已结束')
    await waitFor(() => expect(client.get).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(clearIntervalSpy).toHaveBeenCalled())
    expect(screen.getByRole('textbox', { name: '输入消息' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '发送消息' })).toBeDisabled()
  })

  it.each([
    { products: { product_id: 7 }, label: '对象' },
    { products: 'not-an-array', label: '字符串' },
    { products: [null, { product_id: 7.5 }], label: '空值和小数 ID' },
  ])('falls back to assistant text for malformed products evidence: $label', async ({ products }) => {
    vi.mocked(client.post)
      .mockResolvedValueOnce({ data: { id: 9, status: 'OPEN' } } as never)
      .mockResolvedValueOnce({ data: {
        conversation_id: 9,
        answer: '目录资料暂不可用。',
        intent: 'CATALOG',
        evidence: { products },
      } } as never)

    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))
    fireEvent.change(screen.getByRole('textbox', { name: '输入消息' }), { target: { value: '推荐拍照手机' } })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

    expect(await screen.findByText('目录资料暂不可用。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '查看商品信息' })).not.toBeInTheDocument()
  })
})
