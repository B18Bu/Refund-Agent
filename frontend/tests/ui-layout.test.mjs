import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('主管徽标导航必须在 Badge 根节点继承菜单前景色，避免运行时样式覆盖', () => {
  const shell = read('components/AppShell.tsx')
  const styles = read('styles.css')

  const rootColorOverrides = shell.match(/styles=\{\{ root: \{ color: 'inherit' \} \}\}/g) ?? []
  assert.equal(rootColorOverrides.length, 2)
  assert.match(styles, /\.app-nav-badge\s*\{[^}]*color:\s*inherit/s)
  assert.match(styles, /\.ant-menu-item:focus-visible/)
})

test('核心数据页面必须提供窄屏布局和可滚动表格', () => {
  const dashboard = read('pages/Dashboard.tsx')
  const screen = read('pages/Screen.tsx')
  const styles = read('styles.css')

  assert.match(dashboard, /scroll=\{\{\s*x:/)
  assert.match(screen, /className="screen-stats"/)
  assert.match(screen, /className="screen-charts"/)
  assert.match(styles, /@media\s*\(max-width:\s*768px\)/)
})

test('详情与审批操作必须使用可换行的响应式容器', () => {
  assert.match(read('pages/TicketDetail.tsx'), /className="ticket-detail-header"/)
  assert.match(read('components/ApprovePanel.tsx'), /className="approval-actions"/)
})
