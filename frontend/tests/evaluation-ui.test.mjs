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

test('编排评测中心必须展示节点链路、意图分流和兜底状态', () => {
  const page = read('pages/Evaluations.tsx')
  assert.match(page, /编排评测中心/)
  assert.match(page, /orchestration\.pipeline/)
  assert.match(page, /强信号跳过 LLM/)
  assert.match(page, /orchestration\.fallback\.reasons/)
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

test('工单评测详情仅为主管请求并保留审批区', () => {
  const detail = read('pages/TicketDetail.tsx')
  assert.match(detail, /user\?\.role === 'sv'.*EvaluationDetail/s)
  assert.match(detail, /ApprovePanel/)
  const evaluation = read('components/EvaluationDetail.tsx')
  assert.match(evaluation, /评测暂不可用|暂无评测数据/)
  assert.match(evaluation, /基线输入 Token/)
  assert.match(evaluation, /阶段耗时/)
})

test('工单刷新后必须同步重新请求评测详情', () => {
  const detail = read('pages/TicketDetail.tsx')
  const evaluation = read('components/EvaluationDetail.tsx')
  assert.match(detail, /EvaluationDetail[^>]*refreshVersion=/s)
  assert.match(evaluation, /refreshVersion/)
  assert.match(evaluation, /\[ticketId, refreshVersion\]/)
})

test('无真实评测时仍展示 Golden 且失败文案不伪造通过数', () => {
  const page = read('pages/Evaluations.tsx')
  assert.doesNotMatch(page, /evaluation_count === 0\)[\s\S]*return/)
  assert.match(page, /golden\.score/)
  assert.match(page, /golden\.max_score/)
})

test('Token 增加必须用文字和绝对值表达增幅', () => {
  const page = read('pages/Evaluations.tsx')
  const detail = read('components/EvaluationDetail.tsx')
  for (const source of [page, detail]) {
    assert.match(source, /增加/)
    assert.match(source, /增幅/)
    assert.match(source, /Math\.abs/)
  }
})
