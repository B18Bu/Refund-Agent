import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import CustomerAssistant from './CustomerAssistant'

vi.mock('../api/client', () => ({ default: { post: vi.fn() } }))

describe('CustomerAssistant', () => {
  afterEach(cleanup)

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
})
