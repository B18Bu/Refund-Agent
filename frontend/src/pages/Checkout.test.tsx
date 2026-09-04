import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import Checkout from './Checkout'

vi.mock('../api/client', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

describe('Checkout', () => {
  afterEach(() => cleanup())
  it('显示模拟支付说明并保留地址选择', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: [{ id: 1, recipient_name: '张三', phone: '13800000000', province: '北京', city: '北京', district: '海淀', detail: '中关村', is_default: true }] } as never)
    render(<MemoryRouter><Checkout /></MemoryRouter>)
    expect(await screen.findByText('模拟支付说明')).toBeInTheDocument()
    expect(screen.getByLabelText('张三 13800000000 北京北京海淀中关村 默认地址')).toBeChecked()
  })

  it('地址为空时创建地址并自动选中', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: [] } as never)
    vi.mocked(client.post).mockResolvedValue({ data: { id: 9, recipient_name: '李四', phone: '13900000000', province: '广东', city: '深圳', district: '南山', detail: '科技园', is_default: true } } as never)
    render(<MemoryRouter><Checkout /></MemoryRouter>)

    fireEvent.click(await screen.findByRole('button', { name: '新建收货地址' }))
    fireEvent.change(screen.getByLabelText('收件人'), { target: { value: '李四' } })
    fireEvent.change(screen.getByLabelText('手机号'), { target: { value: '13900000000' } })
    fireEvent.change(screen.getByLabelText('省'), { target: { value: '广东' } })
    fireEvent.change(screen.getByLabelText('市'), { target: { value: '深圳' } })
    fireEvent.change(screen.getByLabelText('区'), { target: { value: '南山' } })
    fireEvent.change(screen.getByLabelText('详细地址'), { target: { value: '科技园' } })
    fireEvent.click(screen.getByRole('button', { name: '保存地址' }))

    await waitFor(() => expect(client.post).toHaveBeenCalledWith('/shop/addresses', expect.objectContaining({ recipient_name: '李四' })))
    expect(await screen.findByLabelText('李四 13900000000 广东深圳南山科技园 默认地址')).toBeChecked()
  })
})
