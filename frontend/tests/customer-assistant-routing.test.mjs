import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('消费者可从商城进入咨询页，且路由受消费者壳层保护', () => {
  const app = read('App.tsx')
  const shell = read('components/CustomerShell.tsx')

  assert.match(app, /path="\/shop\/assistant" element={<CustomerAssistant \/>}/)
  assert.match(shell, /to="\/shop\/assistant"/)
  assert.match(app, /path="\/shop\/privacy" element={<PrivacyPreferences \/>}/)
  assert.match(shell, /to="\/shop\/privacy"/)
})
