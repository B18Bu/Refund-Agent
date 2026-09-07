import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import CustomerAssistant from './CustomerAssistant'

vi.mock('../api/client', () => ({ default: { post: vi.fn() } }))

describe('CustomerAssistant', () => {
  afterEach(cleanup)

  it('展示带抓取时间的推荐依据', async () => {
    vi.mocked(client.post).mockResolvedValue({
      data: {
        answer: '推荐 vivo X100。',
        personalized: false,
        sources: [{ source_url: 'https://example.test/x100', crawled_at: '2026-09-07T08:30:00' }],
      },
    } as never)

    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
    fireEvent.change(screen.getByRole('textbox', { name: '咨询商品' }), { target: { value: '推荐拍照手机' } })
    fireEvent.click(screen.getByRole('button', { name: '发送咨询' }))

    expect(await screen.findByText('推荐依据')).toBeInTheDocument()
    expect(screen.getByText('抓取时间：2026-09-07T08:30:00')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '查看商品资料来源' })).toHaveAttribute('href', 'https://example.test/x100')
  })

  it('在没有来源时展示降级提示', async () => {
    vi.mocked(client.post).mockResolvedValue({ data: { answer: '暂时没有可核验的商品资料。', personalized: false, sources: [] } } as never)

    render(<MemoryRouter><CustomerAssistant /></MemoryRouter>)
    fireEvent.change(screen.getByRole('textbox', { name: '咨询商品' }), { target: { value: '推荐手机' } })
    fireEvent.click(screen.getByRole('button', { name: '发送咨询' }))

    expect(await screen.findByText('当前回答没有可展示的商品资料来源，请以商城商品详情为准。')).toBeInTheDocument()
  })
})
