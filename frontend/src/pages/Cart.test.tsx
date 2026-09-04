import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import Cart from './Cart'

vi.mock('../api/client', () => ({ default: { get: vi.fn() } }))

describe('Cart', () => {
  it('将服务端购物车金额呈现在购物袋订单摘要中', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: { items: [{ brand: 'xiaomi', product_name: '耳机', variant_name: '标准版', quantity: 2, price: 159 }], total_amount: 318 } } as never)
    render(<MemoryRouter><Cart /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: '购物袋' })).toBeInTheDocument()
    expect(screen.getAllByText('¥318.00')).toHaveLength(2)
  })
})
