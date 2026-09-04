import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import Checkout from './Checkout'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

describe('Checkout', () => {
  it('显示模拟支付说明并保留地址选择', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: [{ id: 1, recipient_name: '张三', phone: '13800000000', province: '北京', city: '北京', district: '海淀', detail: '中关村', is_default: true }] } as never)
    render(<MemoryRouter><Checkout /></MemoryRouter>)
    expect(await screen.findByText('模拟支付说明')).toBeInTheDocument()
    expect(screen.getByLabelText('张三 13800000000 北京北京海淀中关村 默认地址')).toBeChecked()
  })
})
