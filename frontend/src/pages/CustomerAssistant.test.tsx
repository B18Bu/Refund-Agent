import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import CustomerAssistant from './CustomerAssistant'

const seededMessages = vi.hoisted(() => ({ value: undefined as unknown }))

vi.mock('../api/client', () => ({ default: { post: vi.fn() } }))
vi.mock('react', async () => {
  const actual = await vi.importActual<typeof import('react')>('react')
  return {
    ...actual,
    useState: <T,>(initial: T) => actual.useState(Array.isArray(initial) && initial.length === 0 && seededMessages.value !== undefined ? seededMessages.value as T : initial),
  }
})

describe('CustomerAssistant', () => {
  afterEach(() => { cleanup(); seededMessages.value = undefined })

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

  it('opens the referenced catalog product without exposing the recommendation text or source links', async () => {
    vi.mocked(client.post)
      .mockResolvedValueOnce({ data: { id: 9, status: 'OPEN' } } as never)
      .mockResolvedValueOnce({ data: {
        conversation_id: 9,
        answer: '推荐这款旗舰影像手机。',
        intent: 'CATALOG',
        evidence: { products: [{ product_id: 7, source_url: 'https://example.com/products/7' }, { product_id: 8, source_url: 'https://example.com/products/8' }, { product_id: 0, source_url: 'https://example.com/invalid' }] },
      } } as never)

    render(<MemoryRouter initialEntries={['/shop']}><Routes><Route path="*" element={<CustomerAssistant />} /><Route path="/shop/products/7" element={<p>商品 7 详情页</p>} /><Route path="/shop/products/8" element={<p>商品 8 详情页</p>} /></Routes></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: '打开智能客服' }))
    fireEvent.change(screen.getByRole('textbox', { name: '输入消息' }), { target: { value: '推荐拍照手机' } })
    fireEvent.click(screen.getByRole('button', { name: '发送消息' }))

    const productButtons = await screen.findAllByRole('button', { name: '查看商品信息' })
    expect(productButtons).toHaveLength(1)
    expect(screen.queryByText('推荐这款旗舰影像手机。')).not.toBeInTheDocument()
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
