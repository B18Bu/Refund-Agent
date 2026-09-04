export type Role = 'customer' | 'cs' | 'sv'

export type SessionUser = {
  id: string
  role: Role
}

function decodeBase64Url(value: string): string {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
  return decodeURIComponent(
    atob(padded)
      .split('')
      .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, '0')}`)
      .join(''),
  )
}

export function getSessionUser(): SessionUser | null {
  const token = localStorage.getItem('token')
  if (!token) return null

  try {
    const payload = JSON.parse(decodeBase64Url(token.split('.')[1]))
    if ((payload.role !== 'customer' && payload.role !== 'cs' && payload.role !== 'sv') || !payload.sub) return null
    return { id: String(payload.sub), role: payload.role }
  } catch {
    return null
  }
}
