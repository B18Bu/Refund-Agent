# 登录页测试账号快捷填充实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让测试人员通过两个浅色虚线按钮填写客服或主管的既有演示凭据，仍由用户手动提交登录。

**架构：** `Login` 组件取得 Ant Design 表单实例；两个 `htmlType="button"` 按钮调用 `setFieldsValue`。前端静态测试直接验证按钮语义、凭据和样式，后端认证与 RBAC 不变。

**技术栈：** React、TypeScript、Ant Design、Node 内置测试、Vite。

---

### 任务 1：登录页快捷填充

**文件：**
- 修改：`frontend/tests/ui-layout.test.mjs`
- 修改：`frontend/src/pages/Login.tsx`

- [ ] **步骤 1：编写失败的测试**

```js
test('登录页测试快捷键只填入演示凭据且不提交表单', () => {
  const login = read('pages/Login.tsx')

  assert.match(login, /const \[form\] = Form\.useForm\(\)/)
  assert.match(login, /form\.setFieldsValue\(\{ username: 'cs1', password: 'secret123' \}\)/)
  assert.match(login, /form\.setFieldsValue\(\{ username: 'sv1', password: 'secret123' \}\)/)
  assert.match(login, /htmlType="button"/)
  assert.match(login, /type="dashed"/)
})
```

- [ ] **步骤 2：运行测试验证失败**

运行：`node --test frontend/tests/ui-layout.test.mjs`

预期：FAIL，原因是当前登录页没有表单实例和快捷填充按钮。

- [ ] **步骤 3：编写最少实现代码**

```tsx
const [form] = Form.useForm()

<Form form={form} layout="vertical" onFinish={onFinish}>
  <Form.Item label="测试账号快捷填充">
    <Space>
      <Button type="dashed" htmlType="button" onClick={() => form.setFieldsValue({ username: 'cs1', password: 'secret123' })}>客服账号</Button>
      <Button type="dashed" htmlType="button" onClick={() => form.setFieldsValue({ username: 'sv1', password: 'secret123' })}>主管账号</Button>
    </Space>
  </Form.Item>
</Form>
```

- [ ] **步骤 4：运行测试验证通过**

运行：`node --test frontend/tests/ui-layout.test.mjs`

预期：PASS，快捷键测试和现有布局测试全部通过。

- [ ] **步骤 5：验证构建与本地交互**

运行：`npm run build`（目录：`frontend`）。

预期：TypeScript 与 Vite 构建成功；在 `/login` 点击两个按钮后，用户名与密码字段分别被填入对应演示凭据，页面不跳转。

- [ ] **步骤 6：Commit**

```bash
git add frontend/src/pages/Login.tsx frontend/tests/ui-layout.test.mjs docs/superpowers/plans/2026-09-01-login-test-shortcuts.md
git commit -m "feat(登录): 增加测试账号快捷填充"
git push origin main
```
