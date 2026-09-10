import axios from 'axios'
import { clearSessionToken, getSessionToken } from '../auth/session'

const client = axios.create({ baseURL: '/api' })

client.interceptors.request.use((cfg) => {
  const t = getSessionToken()
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

client.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      clearSessionToken()
      if (window.location.pathname !== '/login') window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export default client
