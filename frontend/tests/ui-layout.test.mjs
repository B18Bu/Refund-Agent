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

test('工单详情必须展示脱敏的动作层策略审计状态', () => {
  const detail = read('pages/TicketDetail.tsx')

  assert.match(detail, /action_policy\?:\s*\{\s*allowed:\s*boolean;\s*reason:\s*string\s*}/s)
  assert.match(detail, /label="动作层策略"/)
  assert.match(detail, /ACTION_POLICY_CN/)
  assert.match(detail, /未识别策略原因/)
})

test('登录页测试快捷键只填入演示凭据且不提交表单', () => {
  const login = read('pages/Login.tsx')
  const styles = read('styles.css')

  assert.match(login, /const \[form\] = Form\.useForm\(\)/)
  assert.match(login, /form\.setFieldsValue\(\{ username: 'cs1', password: 'secret123' \}\)/)
  assert.match(login, /form\.setFieldsValue\(\{ username: 'sv1', password: 'secret123' \}\)/)
  assert.match(login, /htmlType="button"/)
  assert.match(login, /className="login-test-shortcuts__button"/)
  assert.match(styles, /\.login-test-shortcuts__button\.ant-btn\s*\{[^}]*border-style:\s*dashed/s)
})

test('登录页必须提供项目视觉区与独立登录卡片布局', () => {
  const login = read('pages/Login.tsx')
  const styles = read('styles.css')

  assert.match(login, /className="login-visual"/)
  assert.match(login, /className="login-panel"/)
  assert.match(login, /aria-label="风险识别与退款决策流程图"/)
  assert.match(styles, /\.login-page\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1\.1fr\)/s)
  assert.match(styles, /@media[\s\S]*\.login-visual/s)
})
