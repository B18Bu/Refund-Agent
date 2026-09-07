import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import PrivacyPreferences from './PrivacyPreferences'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), put: vi.fn(), delete: vi.fn() } }))

describe('PrivacyPreferences', () => {
  it('开启授权后可编辑、删除并恢复偏好', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: { enabled: false, preferences: [], ignored_keys: ['brand'] } } as never)
    vi.mocked(client.put).mockResolvedValue({ data: { enabled: true, preferences: [{ key: 'brand', value: ['vivo'], manual: true }], ignored_keys: ['brand'] } } as never)
    vi.mocked(client.delete).mockResolvedValue({ data: { enabled: true, preferences: [{ key: 'brand', value: ['vivo'], manual: true }], ignored_keys: [] } } as never)

    render(<MemoryRouter><PrivacyPreferences /></MemoryRouter>)

    expect(await screen.findByText('未开启')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('switch', { name: '个性化偏好授权' }))
    expect(await screen.findByText('已开启')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '编辑品牌偏好' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '恢复品牌偏好' }))
    expect(client.delete).toHaveBeenCalledWith('/customer-assistant/privacy/ignored/brand')
  })
})
