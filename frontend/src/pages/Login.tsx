import { Form, Input, Button, message } from 'antd'
import client from '../api/client'
import { useNavigate } from 'react-router-dom'

export default function Login() {
  const nav = useNavigate()
  const onFinish = async (v: { username: string; password: string }) => {
    try {
      const { data } = await client.post('/auth/login', v)
      localStorage.setItem('token', data.access_token)
      nav('/')
    } catch (e: any) {
      message.error(e.response?.data?.detail || '登录失败')
    }
  }
  return (
    <div style={{ maxWidth: 320, margin: '120px auto' }}>
      <h2 style={{ textAlign: 'center' }}>客诉舆情退赔决策系统</h2>
      <Form onFinish={onFinish}>
        <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
          <Input placeholder="用户名（cs1=客服 / sv1=主管）" />
        </Form.Item>
        <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
          <Input.Password placeholder="密码" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block>登录</Button>
      </Form>
    </div>
  )
}
