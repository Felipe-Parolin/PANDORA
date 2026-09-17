import axios from 'axios'
import { reactive } from 'vue'

export const auth = reactive({
  user: JSON.parse(localStorage.getItem('pandora_user') || 'null'),
  token: localStorage.getItem('pandora_token'),
})

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api',
})

api.interceptors.request.use((config) => {
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !error.config.url.includes('/auth/login')) logout()
    return Promise.reject(error)
  },
)

export async function login(email, password) {
  const { data } = await api.post('/auth/login/', { email, password })
  auth.token = data.access
  auth.user = data.user
  localStorage.setItem('pandora_token', data.access)
  localStorage.setItem('pandora_refresh', data.refresh)
  localStorage.setItem('pandora_user', JSON.stringify(data.user))
}

export function logout() {
  auth.user = null
  auth.token = null
  localStorage.removeItem('pandora_token')
  localStorage.removeItem('pandora_refresh')
  localStorage.removeItem('pandora_user')
  if (location.pathname !== '/login') location.assign('/login')
}

export const rows = (data) => data?.results || data || []
export const can = (permission) => Boolean(auth.user?.permissions?.includes('*') || auth.user?.permissions?.includes(permission))
export const money = (value) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value || 0))
export const shortDate = (value) => value ? new Intl.DateTimeFormat('pt-BR').format(new Date(`${value}T12:00:00`)) : '—'
export const apiError = (error) => {
  const data = error.response?.data
  if (!data) return 'Não foi possível concluir a operação.'
  if (typeof data === 'string') return data
  if (data.detail) return data.detail
  const first = Object.values(data)[0]
  return Array.isArray(first) ? first[0] : (typeof first === 'object' ? JSON.stringify(first) : first)
}
