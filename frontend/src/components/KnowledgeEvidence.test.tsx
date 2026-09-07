import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import client from '../api/client'
import KnowledgeEvidence from './KnowledgeEvidence'

vi.mock('../api/client', () => ({ default: { get: vi.fn() } }))

describe('KnowledgeEvidence', () => {
  afterEach(() => {
    cleanup()
    vi.resetAllMocks()
  })

  it('请求进行中时展示加载骨架', () => {
    vi.mocked(client.get).mockReturnValue(new Promise(() => {}) as never)

    const { container } = render(<KnowledgeEvidence endpoint="/tickets/8/knowledge" />)

    expect(container.querySelector('.ant-skeleton')).toBeInTheDocument()
  })

  it('未命中政策时展示空结果', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: { available: true, status: 'empty', results: [] } } as never)

    render(<KnowledgeEvidence endpoint="/tickets/8/knowledge" />)

    expect(await screen.findByText('未检索到匹配的政策原文')).toBeInTheDocument()
  })

  it('检索服务不可用时说明不会影响工单处理', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: { available: false, status: 'unavailable', results: [] } } as never)

    render(<KnowledgeEvidence endpoint="/tickets/8/knowledge" />)

    expect(await screen.findByText('政策依据暂不可用')).toBeInTheDocument()
    expect(screen.getByText('不影响现有工单处理。')).toBeInTheDocument()
  })

  it('请求失败时降级提示不会影响工单处理', async () => {
    vi.mocked(client.get).mockRejectedValue(new Error('embedding service unavailable'))

    render(<KnowledgeEvidence endpoint="/tickets/8/knowledge" />)

    expect(await screen.findByText('政策依据暂不可用')).toBeInTheDocument()
    expect(screen.getByText('不影响现有工单处理。')).toBeInTheDocument()
  })

  it('展示原文及其来源、章节、版本和三位相似度', async () => {
    vi.mocked(client.get).mockResolvedValue({
      data: {
        available: true,
        status: 'ok',
        results: [{
          content: '金额超限的订单必须转人工审批。',
          source: 'docs/guides/refund-policy.md',
          section: '3.2 金额阈值',
          version: 'v2026.09',
          similarity: 0.98765,
        }],
      },
    } as never)

    render(<KnowledgeEvidence endpoint="/tickets/8/knowledge" />)

    expect(await screen.findByText('金额超限的订单必须转人工审批。')).toBeInTheDocument()
    expect(screen.getByText('来源：docs/guides/refund-policy.md')).toBeInTheDocument()
    expect(screen.getByText('章节：3.2 金额阈值')).toBeInTheDocument()
    expect(screen.getByText('版本：v2026.09')).toBeInTheDocument()
    expect(screen.getByText('相似度：0.988')).toBeInTheDocument()
  })

  it('endpoint 变更后重新请求新地址', async () => {
    vi.mocked(client.get).mockResolvedValue({ data: { available: true, status: 'empty', results: [] } } as never)

    const { rerender } = render(<KnowledgeEvidence endpoint="/tickets/8/knowledge" />)
    await waitFor(() => expect(client.get).toHaveBeenCalledWith('/tickets/8/knowledge'))

    rerender(<KnowledgeEvidence endpoint="/evaluations/knowledge" />)

    await waitFor(() => expect(client.get).toHaveBeenLastCalledWith('/evaluations/knowledge'))
    expect(client.get).toHaveBeenCalledTimes(2)
  })
})
