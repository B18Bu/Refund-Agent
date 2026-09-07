import { Button, Input, Spin, Switch } from 'antd'
import { useEffect, useState } from 'react'
import client from '../api/client'
import type { CustomerPrivacyState } from '../types/shop'

const labels: Record<string, string> = {
  category: '品类', brand: '品牌', size: '尺寸', budget: '预算', purchase_frequency: '购买频率', recent_products: '最近购买商品',
}

export default function PrivacyPreferences() {
  const [state, setState] = useState<CustomerPrivacyState>()
  const [editing, setEditing] = useState<string>()
  const [value, setValue] = useState('')
  const [failed, setFailed] = useState(false)

  const load = () => client.get<CustomerPrivacyState>('/customer-assistant/privacy').then((response) => setState(response.data)).catch(() => setFailed(true))
  useEffect(() => { void load() }, [])

  const updateState = (request: Promise<{ data: CustomerPrivacyState }>) => {
    setFailed(false)
    request.then((response) => setState(response.data)).catch(() => setFailed(true))
  }
  const toggle = (enabled: boolean) => updateState(client.put('/customer-assistant/privacy', { enabled }))
  const startEdit = (key: string, preferenceValue: unknown) => {
    setEditing(key)
    setValue(JSON.stringify(preferenceValue))
  }
  const save = (key: string) => {
    try {
      updateState(client.put(`/customer-assistant/privacy/preferences/${key}`, { value: JSON.parse(value) }))
      setEditing(undefined)
    } catch {
      setFailed(true)
    }
  }

  if (!state) return <main className="page-wrap privacy-preferences" aria-live="polite">{failed ? <p role="alert">隐私设置暂时无法加载，请稍后重试。</p> : <Spin />}</main>

  return <main className="page-wrap privacy-preferences" aria-labelledby="privacy-preferences-title">
    <section className="privacy-preferences__intro">
      <p className="shop-eyebrow">个性化控制</p><h1 id="privacy-preferences-title">隐私偏好</h1>
      <p>仅在您授权后，系统才会使用有效订单中的商品信息生成偏好。关闭后会清除已生成的偏好画像。</p>
    </section>
    <section className="privacy-preferences__consent" aria-label="个性化偏好授权设置">
      <div><strong>{state.enabled ? '已开启' : '未开启'}</strong><span>允许使用商品购买记录生成偏好</span></div>
      <Switch aria-label="个性化偏好授权" checked={state.enabled} onChange={toggle} />
    </section>
    {failed && <p className="privacy-preferences__error" role="alert">操作未完成，请稍后重试。</p>}
    {state.enabled && <section className="privacy-preferences__list" aria-labelledby="privacy-preferences-list">
      <h2 id="privacy-preferences-list">当前偏好</h2>
      {state.preferences.length ? <ul>{state.preferences.map((preference) => <li key={preference.key}>
        <div><strong>{labels[preference.key] || preference.key}</strong><span>{JSON.stringify(preference.value)}</span></div>
        <div className="privacy-preferences__actions">
          <Button onClick={() => startEdit(preference.key, preference.value)} aria-label={`编辑${labels[preference.key] || preference.key}偏好`}>编辑</Button>
          <Button danger onClick={() => updateState(client.delete(`/customer-assistant/privacy/preferences/${preference.key}`))} aria-label={`删除${labels[preference.key] || preference.key}偏好`}>删除</Button>
        </div>
        {editing === preference.key && <div className="privacy-preferences__editor"><Input.TextArea aria-label={`${labels[preference.key] || preference.key}偏好值`} value={value} onChange={(event) => setValue(event.target.value)} /><Button type="primary" onClick={() => save(preference.key)}>保存</Button></div>}
      </li>)}</ul> : <p>暂无已生成的偏好。</p>}
    </section>}
    <section className="privacy-preferences__ignored" aria-labelledby="privacy-preferences-ignored">
      <h2 id="privacy-preferences-ignored">已忽略偏好</h2>
      {state.ignored_keys.length ? <ul>{state.ignored_keys.map((key) => <li key={key}><span>{labels[key] || key}</span><Button onClick={() => updateState(client.delete(`/customer-assistant/privacy/ignored/${key}`))} aria-label={`恢复${labels[key] || key}偏好`}>恢复</Button></li>)}</ul> : <p>暂无已忽略偏好。</p>}
    </section>
  </main>
}
