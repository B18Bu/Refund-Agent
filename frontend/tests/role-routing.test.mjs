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

test('客服后台菜单不暴露商城交易入口', () => {
  const shell = read('components/AppShell.tsx')
  const csItems = shell.match(/const csItems = \[([\s\S]*?)\n\]/)?.[1]

  assert.ok(csItems, '应显式定义客服后台导航')
  assert.match(csItems, /\/service\/refunds/)
  assert.doesNotMatch(csItems, /\/shop/)
})

test('客服只能使用退款审核路由，其他后台页面由主管守卫', () => {
  const app = read('App.tsx')

  assert.match(app, /path="\/service\/refunds" element={<ServiceRefunds \/>}/)
  assert.match(app, /path="\/workspace" element={<SupervisorOnly><Dashboard showScreen \/><\/SupervisorOnly>}/)
  assert.match(app, /path="\/my-tickets" element={<SupervisorOnly><MyTickets \/><\/SupervisorOnly>}/)
  assert.match(app, /path="\/process" element={<SupervisorOnly><ProcessOverview \/><\/SupervisorOnly>}/)
})

test('退款申请先上传受控凭证，客服使用专用退款队列', () => {
  const orderDetail = read('pages/OrderDetail.tsx')
  const serviceRefunds = read('pages/ServiceRefunds.tsx')

  assert.match(orderDetail, /\/shop\/return-evidence/)
  assert.match(orderDetail, /storage_keys/)
  assert.doesNotMatch(orderDetail, /evidence_paths:\s*files\.map/)
  assert.match(serviceRefunds, /\/tickets\/service\/returns/)
  assert.match(serviceRefunds, /\/tickets\/\$\{.*\}\/approve/)
})

test('价格专区以分为边界连续覆盖全部可售商品', () => {
  const home = read('pages/ShopHome.tsx')

  assert.match(home, /max_price: 300/)
  assert.match(home, /min_price: 300\.01, max_price: 3000/)
  assert.match(home, /min_price: 3000\.01/)
})
