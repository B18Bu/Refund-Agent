import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import ProductDetail from './ProductDetail'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), put: vi.fn() } }))

describe('ProductDetail', () => {
  it('展示服务端商品的官方目录价格和加入购物车操作', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: {
      id: 1, brand: 'xiaomi', name: 'Xiaomi 真无线耳机', image_url: 'https://example.test/product.png', status: 'ACTIVE',
      variants: [{ id: 11, sku: 'ear-1', variant_name: '标准版', price: 159, available: true }],
    } } as never)
    render(<MemoryRouter initialEntries={['/shop/products/1']}><Routes><Route path="/shop/products/:id" element={<ProductDetail />} /></Routes></MemoryRouter>)
    expect(await screen.findByText('官方目录价格')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '加入购物车' })).toBeEnabled()
  })
})
