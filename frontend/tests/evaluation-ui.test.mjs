import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('评测中心必须是主管路由并显示真实数据来源', () => {
  assert.match(read('App.tsx'), /path="\/evaluations".*SupervisorOnly/s)
  const page = read('pages/Evaluations.tsx')
  assert.match(page, /measurement_type/)
  assert.match(page, /暂无评测数据/)
  assert.doesNotMatch(page, /64\.4/)
})

test('评测图表必须提供错误恢复和可见数据后备', () => {
  const page = read('pages/Evaluations.tsx')
  assert.match(page, /重新加载/)
  assert.match(page, /Token 数值明细/)
  assert.match(page, /近 7 日数值/)
  assert.match(page, /onKeyDown/)
})

test('评测中心必须具备响应式网格和可见焦点', () => {
  const styles = read('styles.css')
  assert.match(styles, /\.evaluation-kpis/)
  assert.match(styles, /\.evaluation-row:focus-visible/)
  assert.match(styles, /@media\s*\(max-width:\s*640px\)/)
})
