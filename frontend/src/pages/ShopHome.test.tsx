import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import ShopHome from './ShopHome'

vi.mock('../api/client', () => ({ default: { get: vi.fn() } }))

const headset = {
  id: 1,
  brand: 'xiaomi',
  name: 'Xiaomi 真无线耳机',
  status: 'ACTIVE',
  variants: [{ id: 11, sku: 'ear-1', variant_name: '标准版', price: 159, available: true }],
}

const phone = {
  id: 2,
  brand: 'vivo',
  name: 'vivo X 系列手机',
  status: 'ACTIVE',
  variants: [{ id: 21, sku: 'phone-1', variant_name: '标准版', price: 3999, available: true }],
}

describe('ShopHome', () => {
  it('只展示目录中存在的分类，并标注 vivo 与小米官方目录', async () => {
    vi.mocked(client.get).mockImplementation((url) => Promise.resolve(
      url === '/shop/brands' ? { data: ['vivo', 'xiaomi'] } : { data: { items: [headset, phone] } },
    ) as never)

    render(<MemoryRouter><ShopHome /></MemoryRouter>)

    expect(await screen.findByText('vivo · 小米官方目录')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '耳机' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '平板' })).not.toBeInTheDocument()
  })
})
