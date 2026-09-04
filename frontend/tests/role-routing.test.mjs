import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('登录页提供三类预置账号的快捷填充', () => {
  const login = read('pages/Login.tsx')

  assert.match(login, /customer_01/)
  assert.match(login, /customer_service_01/)
  assert.match(login, /supervisor_01/)
  assert.match(login, /password: 'secret123'/)
})

test('不同账号登录后进入职责对应的首页', () => {
  const app = read('App.tsx')
  const login = read('pages/Login.tsx')

  assert.match(app, /user\?\.role === 'customer' \? '\/shop'/)
  assert.match(app, /user\?\.role === 'cs' \? '\/service\/refunds'/)
  assert.match(login, /role === 'customer' \? '\/shop'/)
  assert.match(login, /role === 'cs' \? '\/service\/refunds'/)
})

test('消费者使用独立商城壳层，且壳层没有退款工作台导航', () => {
  const app = read('App.tsx')
  const shell = read('components/CustomerShell.tsx')

  assert.match(app, /<Route element={<CustomerShell \/>}>/)
  assert.match(shell, /购物车/)
  assert.match(shell, /我的订单/)
  assert.match(shell, /退款售后/)
  assert.doesNotMatch(shell, /退款工作台/)
})
