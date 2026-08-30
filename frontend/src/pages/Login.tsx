import { Form, Input, Button, message } from 'antd'
import client from '../api/client'
import { useNavigate } from 'react-router-dom'
import { getSessionUser } from '../types/auth'

export default function Login() {
  const nav = useNavigate()
  const onFinish = async (v: { username: string; password: string }) => {
    try {
      const { data } = await client.post('/auth/login', v)
      localStorage.setItem('token', data.access_token)
      nav(getSessionUser()?.role === 'sv' ? '/monitor' : '/my-tickets')
    } catch (e: any) {
      message.error(e.response?.data?.detail || '登录失败')
    }
  }
  return (
    <main className="login-page">
      <div className="login-panel">
      <h1>客诉舆情退赔决策系统</h1>
      <Form layout="vertical" onFinish={onFinish}>
        <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名' }]}>
          <Input placeholder="用户名（cs1=客服 / sv1=主管）" />
        </Form.Item>
        <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }]}>
          <Input.Password placeholder="密码" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block>登录</Button>
      </Form>
      </div>
    </main>
  )
}
