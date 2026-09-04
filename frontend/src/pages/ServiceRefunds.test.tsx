import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import ServiceRefunds from './ServiceRefunds'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

describe('ServiceRefunds', () => {
  it('在订单与退单页签分别展示客服可见记录，并只允许审批待人工审核退单', async () => {
    vi.mocked(client.get).mockImplementation((url) => Promise.resolve({
      data: url === '/tickets/service/orders'
        ? [{ id: 1, order_no: 'O-001', username: 'buyer', total_amount: 128, currency: 'CNY', status: 'PAID_SIMULATED', items: [{ id: 1, product_name: 'X100', quantity: 1, unit_price: 128, status: 'NORMAL' }] }]
        : [
            { id: 1, ticket_id: 8, return_no: 'R-001', order_no: 'O-001', username: 'buyer', status: 'PENDING_REVIEW', can_approve: true, amount: 128, evidence_paths: [], decision_reasons: [] },
            { id: 2, ticket_id: 9, return_no: 'R-002', order_no: 'O-002', username: 'buyer', status: 'PROCESSING', can_approve: false, amount: 256, evidence_paths: [], decision_reasons: [] },
          ],
    } as never))

    render(<ServiceRefunds />)

    expect(await screen.findByRole('tab', { name: '订单申请' })).toBeInTheDocument()
    expect(screen.getByText('O-001')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('tab', { name: '退单申请' }))

    expect(await screen.findByText('R-002')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: '批准退款' })).toHaveLength(1)
  })
})
