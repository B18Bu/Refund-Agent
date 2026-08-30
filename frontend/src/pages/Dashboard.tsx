import { useEffect, useState } from 'react'
import { Alert, Table, Button, InputNumber, Tag, message, Typography, Modal, Upload, Form, Empty } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import client from '../api/client'
import { useNavigate } from 'react-router-dom'

type Row = {
  id: number
  ticket_no: string
  amount: number
  status: string
  status_text: string
  outcome: string
  outcome_text: string
  fraud_score: number | null
  sentiment: string | null
  sentiment_text: string | null
  error_code: string | null
  created_at: string | null
}

const statusColor: Record<string, string> = {
  RUNNING: 'blue',
  SUSPENDED: 'gold',
  COMPLETED: 'green',
}

const outcomeColor: Record<string, string> = {
  PENDING: 'default',
  AUTO_REFUNDED: 'cyan',
  APPROVED: 'green',
  REJECTED: 'red',
  FAILED: 'volcano',
}

// 舆情等级英文→中文兜底（后端已返回 sentiment_text，此处备用）
const sentimentCN: Record<string, string> = { LOW: '低', MEDIUM: '中', HIGH: '高' }

export default function Dashboard({ title = '退赔工单工作台', showScreen = false }: { title?: string; showScreen?: boolean }) {
  const [rows, setRows] = useState<Row[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [amount, setAmount] = useState<number>(128)
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const nav = useNavigate()

  const load = async () => {
    setListLoading(true)
    try {
      const { data } = await client.get('/tickets')
      setRows(data)
      setListError(null)
    } catch (e: any) {
      setListError(e.response?.data?.detail || '退款申请加载失败，请重试')
    } finally {
      setListLoading(false)
    }
  }
  useEffect(() => {
    void load()
    const timer = setInterval(() => { void load() }, 5000)
    return () => clearInterval(timer)
  }, [])

  const create = async () => {
    setLoading(true)
    try {
      // multipart：一次建单 + 上传凭证，保证 Worker 消费时图片已就绪
      const form = new FormData()
      form.append('amount', String(amount))
      for (const f of fileList) {
        if (f.originFileObj) form.append('files', f.originFileObj)
      }
      await client.post('/tickets/with-files', form, {
        headers: { 'X-Idempotency-Key': crypto.randomUUID(), 'Content-Type': 'multipart/form-data' },
      })
      message.success('已提交申请')
      setModalOpen(false)
      setFileList([])
      void load()
    } catch (e: any) {
      message.error(e.response?.data?.detail || '提交失败')
    } finally {
      setLoading(false)
    }
  }

  const cols = [
    { title: '工单号', dataIndex: 'ticket_no' },
    { title: '金额', dataIndex: 'amount', render: (v: number) => `¥${v}` },
    { title: '状态', dataIndex: 'status_text', render: (_: string, r: Row) => <Tag color={statusColor[r.status]}>{r.status_text || r.status}</Tag> },
    { title: '结果', dataIndex: 'outcome_text', render: (_: string, r: Row) => <Tag color={outcomeColor[r.outcome]}>{r.outcome_text || r.outcome}</Tag> },
    { title: '欺诈分', dataIndex: 'fraud_score', render: (v: number | null) => v ?? '-' },
    { title: '舆情', dataIndex: 'sentiment_text', render: (_: string, r: Row) => r.sentiment_text ?? sentimentCN[r.sentiment ?? ''] ?? '-' },
    { title: '错误', dataIndex: 'error_code', render: (v: string | null) => v ?? '-' },
  ]

  return (
    <div>
      <div className="page-header">
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>{title}</Typography.Title>
          <Typography.Text type="secondary">统一查看申请状态、风险结果和处理异常</Typography.Text>
        </div>
        <div className="page-header__actions">
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>新建退款申请</Button>
          {showScreen && <Button onClick={() => nav('/screen')}>进入大屏</Button>}
        </div>
      </div>

      <Modal
        title="新建退款申请"
        open={modalOpen}
        onOk={create}
        onCancel={() => { setModalOpen(false); setFileList([]) }}
        confirmLoading={loading}
        okText="提交"
        cancelText="取消"
      >
        <Form layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="退款金额（元）" required>
            <InputNumber value={amount} onChange={(v) => setAmount(v ?? 0)} min={0.01} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="凭证图片（建议上传清晰订单/商品图，最多 3 张）">
            <Upload
              listType="picture-card"
              fileList={fileList}
              beforeUpload={() => false}
              onChange={({ fileList: fl }) => setFileList(fl.slice(0, 3))}
              accept="image/jpeg,image/png"
            >
              {fileList.length >= 3 ? null : (
                <div><PlusOutlined /><div style={{ marginTop: 8 }}>上传</div></div>
              )}
            </Upload>
          </Form.Item>
          <Typography.Text type="secondary">
            提示：不上传凭证或凭证模糊时，系统将转人工审核（OCR 置信度 {'<'} 60% 强制人工）。
          </Typography.Text>
        </Form>
      </Modal>
      {listError && (
        <Alert
          type="error"
          showIcon
          message="退款申请加载失败"
          description={listError}
          action={<Button size="small" onClick={() => void load()}>重试</Button>}
          style={{ marginBottom: 16 }}
        />
      )}
      <div className="surface">
        <Table
          rowKey="id"
          loading={listLoading}
          locale={{ emptyText: <Empty description="暂无退款申请" /> }}
          dataSource={rows}
          columns={cols}
          scroll={{ x: 900 }}
          pagination={{ pageSize: 10 }}
          onRow={(r) => ({
            onClick: () => nav(`/ticket/${r.id}`),
            onKeyDown: (event) => {
              if (event.key === 'Enter') nav(`/ticket/${r.id}`)
            },
            tabIndex: 0,
            'aria-label': `查看工单 ${r.ticket_no}`,
            style: { cursor: 'pointer' },
          })}
        />
      </div>
    </div>
  )
}
