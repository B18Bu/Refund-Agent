import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AppShell from './AppShell'
import client from '../api/client'

vi.mock('../api/client', () => ({ default: { get: vi.fn() } }))

function supervisorToken() {
  return `x.${btoa(JSON.stringify({ sub: 'supervisor-1', role: 'sv' })).replace(/=/g, '')}.x`
}

describe('AppShell', () => {
  afterEach(() => localStorage.clear())

  it('在运营侧栏使用反白品牌标识', () => {
    localStorage.setItem('token', supervisorToken())
    vi.mocked(client.get).mockResolvedValue({ data: [] } as never)

    render(<MemoryRouter initialEntries={['/workspace']}><Routes><Route element={<AppShell />}><Route path="/workspace" element={<div>工作台</div>} /></Route></Routes></MemoryRouter>)

    expect(screen.getByRole('img', { name: '退赔决策控制台 Logo' })).toBeInTheDocument()
    expect(screen.getByText('退赔决策控制台')).toBeInTheDocument()
  })
})
