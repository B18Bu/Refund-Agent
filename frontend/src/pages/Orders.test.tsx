import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import Orders from './Orders'

vi.mock('../api/client', () => ({ default: { get: vi.fn() } }))

describe('Orders', () => {
  it('以商城订单卡片展示服务端订单金额与状态', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: [{ id: 1, order_no: 'ORD-001', status: 'PAID_SIMULATED', total_amount: 159, currency: 'CNY', address_snapshot_json: {}, items: [] }] } as never)
    render(<MemoryRouter><Orders /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: '我的订单' })).toBeInTheDocument()
    expect(screen.getByText('订单状态')).toBeInTheDocument()
  })
})
