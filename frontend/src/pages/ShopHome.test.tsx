import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
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
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('以确定性分类参数加载手机专区，而不是依赖名称关键词', async () => {
    vi.mocked(client.get).mockImplementation((url) => Promise.resolve(
      url === '/shop/brands' ? { data: ['vivo'] } : { data: { items: [phone] } },
    ) as never)

    render(<MemoryRouter initialEntries={['/shop?category=PHONE']}><ShopHome /></MemoryRouter>)

    await waitFor(() => expect(client.get).toHaveBeenCalledWith('/shop/products', expect.objectContaining({ params: expect.objectContaining({ category: 'PHONE' }) })))
  })

  it('以主会场、快捷分类和服务承诺组织官方目录', async () => {
    vi.mocked(client.get).mockImplementation((url) => Promise.resolve(
      url === '/shop/brands' ? { data: ['vivo', 'xiaomi'] } : { data: { items: [headset, phone] } },
    ) as never)

    render(<MemoryRouter><ShopHome /></MemoryRouter>)

    expect(await screen.findByRole('region', { name: '商城主会场' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '商品快捷分类' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '外设' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '平板' })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: '商城服务承诺' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: '全部商品分类' })).not.toBeInTheDocument()
    expect(screen.queryByRole('complementary', { name: '用户服务' })).not.toBeInTheDocument()
  })
})
