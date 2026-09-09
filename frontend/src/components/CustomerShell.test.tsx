import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import CustomerShell from './CustomerShell'
import stylesheet from '../styles.css?inline'

function customerToken() {
  return `x.${btoa(JSON.stringify({ sub: 'customer-1', role: 'customer' })).replace(/=/g, '')}.x`
}

describe('CustomerShell', () => {
  afterEach(() => localStorage.clear())

  it('为商城提供紧凑导航、搜索和悬浮客服', () => {
    localStorage.setItem('token', customerToken())

    render(<MemoryRouter initialEntries={['/shop']}><Routes><Route element={<CustomerShell />}><Route path="/shop" element={<div>商城内容</div>} /></Route></Routes></MemoryRouter>)

    expect(screen.queryByRole('navigation', { name: '商城工具栏' })).not.toBeInTheDocument()
    expect(screen.getByRole('search', { name: '搜索商城商品' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: '商城主导航' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '全部商品分类' })).toHaveAttribute('href', '/shop')
    expect(screen.getByRole('link', { name: '我的' })).toHaveAttribute('href', '/shop/account')
    expect(screen.queryByRole('link', { name: '智能客服' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '打开智能客服' })).toBeInTheDocument()
  })

  it('移动端不隐藏订单、购物车或退出登录入口', () => {
    expect(stylesheet).not.toMatch(/\.customer-header__actions\s*\{\s*display:\s*none;\s*\}/)
    expect(stylesheet).not.toMatch(/\.customer-header__actions a:first-child,\s*\.customer-header__actions button\s*\{\s*display:\s*none;\s*\}/)
    expect(stylesheet).not.toMatch(/\.customer-main-nav\s*>\s*a:nth-last-child\(-n\+2\)\s*\{\s*display:\s*none;\s*\}/)
  })
})
