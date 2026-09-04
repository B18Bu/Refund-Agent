import { Form, Input, Button, Space, message } from 'antd'
import client from '../api/client'
import { useNavigate } from 'react-router-dom'
import { getSessionUser } from '../types/auth'

export default function Login() {
  const nav = useNavigate()
  const [form] = Form.useForm()
  const onFinish = async (v: { username: string; password: string }) => {
    try {
      const { data } = await client.post('/auth/login', v)
      localStorage.setItem('token', data.access_token)
      const role = getSessionUser()?.role
      nav(role === 'customer' ? '/shop' : role === 'cs' ? '/service/refunds' : '/monitor')
    } catch (e: any) {
      message.error(e.response?.data?.detail || '登录失败')
    }
  }
  return (
    <main className="login-page">
      <section className="login-visual" aria-label="风险识别与退款决策流程图">
        <div className="login-visual__brand"><span className="login-visual__mark">R</span><span>Refund Agent</span></div>
        <div className="login-visual__copy">
          <p className="login-visual__eyebrow">AI GOVERNANCE CONSOLE</p>
          <h2>让每一次退赔决策<br />都有迹可循</h2>
          <p>从客诉信息到风险判断，统一沉淀为可审计、可解释的处理流程。</p>
        </div>
        <svg className="login-visual__diagram" viewBox="0 0 560 260" role="img" aria-label="投诉信息经过安全识别、风险评估后进入人工审核或自动决策">
          <defs><linearGradient id="flow-line" x1="0" x2="1"><stop offset="0" stopColor="#8ca9ff" /><stop offset="1" stopColor="#b9a7ff" /></linearGradient></defs>
          <path d="M70 130h115M255 130h50M380 130h110" stroke="url(#flow-line)" strokeWidth="2" strokeDasharray="6 8" />
          <g className="login-visual__node"><rect x="10" y="96" width="120" height="68" rx="12" /><text x="70" y="125" textAnchor="middle">客诉输入</text><text x="70" y="146" textAnchor="middle">OCR / 文本</text></g>
          <g className="login-visual__node"><rect x="195" y="96" width="120" height="68" rx="12" /><text x="255" y="125" textAnchor="middle">安全识别</text><text x="255" y="146" textAnchor="middle">DLP · Critic</text></g>
          <g className="login-visual__node"><rect x="365" y="96" width="120" height="68" rx="12" /><text x="425" y="125" textAnchor="middle">风险评估</text><text x="425" y="146" textAnchor="middle">规则 · Agent</text></g>
          <circle cx="520" cy="130" r="22" fill="#fff" stroke="#a993ff" strokeWidth="2" /><path d="M511 130l6 6 12-14" fill="none" stroke="#7765d8" strokeWidth="3" />
        </svg>
        <div className="login-visual__metrics"><span><strong>100%</strong><small>可追溯</small></span><span><strong>24/7</strong><small>持续守护</small></span><span><strong>0</strong><small>明文外发</small></span></div>
      </section>
      <div className="login-panel">
        <div className="login-panel__intro"><p className="login-panel__eyebrow">欢迎回来</p><h1>登录平台</h1><p>账号将按身份安全进入商城或退款审核工作台</p></div>
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item label="测试账号快捷填充" className="login-test-shortcuts">
            <Space wrap>
              <Button className="login-test-shortcuts__button" type="dashed" htmlType="button" onClick={() => form.setFieldsValue({ username: 'customer_01', password: 'secret123' })}>普通用户演示账号</Button>
              <Button className="login-test-shortcuts__button" type="dashed" htmlType="button" onClick={() => form.setFieldsValue({ username: 'customer_service_01', password: 'secret123' })}>客服演示账号</Button>
              <Button className="login-test-shortcuts__button" type="dashed" htmlType="button" onClick={() => form.setFieldsValue({ username: 'supervisor_01', password: 'secret123' })}>主管演示账号</Button>
            </Space>
          </Form.Item>
          <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}><Input placeholder="请输入预置账号" /></Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}><Input.Password placeholder="密码" /></Form.Item>
          <Button type="primary" htmlType="submit" block>登录</Button>
        </Form>
      </div>
    </main>
  )
}
