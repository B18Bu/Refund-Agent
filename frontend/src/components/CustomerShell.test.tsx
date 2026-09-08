import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import CustomerShell from './CustomerShell'

function customerToken() {
  return `x.${btoa(JSON.stringify({ sub: 'customer-1', role: 'customer' })).replace(/=/g, '')}.x`
}

describe('CustomerShell', () => {
  afterEach(() => localStorage.clear())

  it('为商城提供工具栏、搜索区和主导航', () => {
    localStorage.setItem('token', customerToken())

    render(<MemoryRouter initialEntries={['/shop']}><Routes><Route element={<CustomerShell />}><Route path="/shop" element={<div>商城内容</div>} /></Route></Routes></MemoryRouter>)

    expect(screen.getByRole('navigation', { name: '商城工具栏' })).toBeInTheDocument()
    expect(screen.getByRole('search', { name: '搜索商城商品' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '商城主导航' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '全部商品分类' })).toHaveAttribute('href', '/shop')
    expect(screen.queryByRole('link', { name: '智能客服' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '打开智能客服' })).toBeInTheDocument()
  })
})
