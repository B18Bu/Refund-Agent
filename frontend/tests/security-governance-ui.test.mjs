import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('安全治理中心只对主管提供导航和路由，并明确数据口径', () => {
  assert.match(read('App.tsx'), /path="\/security-governance".*SupervisorOnly/s)
  assert.match(read('components/AppShell.tsx'), /安全治理中心/)

  const page = read('pages/SecurityGovernance.tsx')
  assert.match(page, /最近一次红蓝测试/)
  assert.match(page, /报告暂不可用/)
  assert.match(page, /重新加载/)
  assert.match(page, /数据口径/)
})

test('安全治理图表不能以缺失报告伪造零值，并提供文字后备', () => {
  const page = read('pages/SecurityGovernance.tsx')
  assert.match(page, /available/)
  assert.match(page, /攻击类型数值明细/)
  assert.match(page, /security-governance\/summary/)
  assert.doesNotMatch(page, /categories\s*\?\?.*\[\{.*sample_count:\s*0/s)
})

test('安全治理中心具备局部横向滚动、可见焦点和窄屏单列布局', () => {
  const styles = read('styles.css')
  assert.match(styles, /\.security-governance-table/)
  assert.match(styles, /\.security-governance[^\n]*:focus-visible/)
  assert.match(styles, /@media\s*\(max-width:\s*768px\)/)
  assert.match(styles, /@media\s*\(max-width:\s*640px\)/)
})
