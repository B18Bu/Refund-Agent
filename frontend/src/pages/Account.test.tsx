import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import Account from './Account'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }))

describe('Account', () => {
  it('聚合订单配送状态、地址维护入口与系统定义的偏好标签', async () => {
    vi.mocked(client.get).mockImplementation((url) => {
      if (url === '/shop/orders') return Promise.resolve({ data: [{ id: 1, order_no: 'ORD-001', status: 'PAID_SIMULATED', total_amount: 159, currency: 'CNY', address_snapshot_json: {}, items: [{ id: 1, product_snapshot_json: { name: '手机' }, quantity: 1, unit_price: 159, status: 'PAID' }] }] } as never)
      if (url === '/shop/addresses') return Promise.resolve({ data: [{ id: 1, recipient_name: '张三', phone: '13800000000', province: '北京', city: '北京', district: '海淀', detail: '科技园', is_default: true }] } as never)
      return Promise.resolve({ data: { enabled: false, preferences: [], ignored_keys: [] } } as never)
    })
    render(<MemoryRouter><Account /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: '订单与配送' })).toBeInTheDocument()
    expect(screen.getByText('已支付，等待出库')).toBeInTheDocument()
    expect(screen.getByText('手机 x 1')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '收货地址' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新增地址' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '购物偏好' })).toBeInTheDocument()
    expect(screen.getByText('品牌')).toBeInTheDocument()
    expect(screen.getAllByText('未授权生成').length).toBeGreaterThan(0)
  })
})
