import { ref } from 'vue'
import router from '../router'

const BASE = '/api'

export function useApi() {
  const token = ref(localStorage.getItem('token'))

  async function request(path, options = {}) {
    const headers = { ...options.headers }
    if (token.value) headers['Authorization'] = `Bearer ${token.value}`
    if (options.body && !(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json'
      options.body = JSON.stringify(options.body)
    }
    const res = await fetch(`${BASE}${path}`, { ...options, headers })
    if (res.status === 401 && path !== '/auth/login') {
      token.value = null
      localStorage.removeItem('token')
      router.push('/login')
      throw new Error('Session expired')
    }
    if (!res.ok) throw new Error(await res.text())
    return res.json()
  }

  const get = (path) => request(path)
  const post = (path, body) => request(path, { method: 'POST', body })
  const put = (path, body) => request(path, { method: 'PUT', body })
  const del = (path) => request(path, { method: 'DELETE' })

  async function login(username, password) {
    const data = await request('/auth/login', {
      method: 'POST',
      body: { username, password },
    })
    token.value = data.access_token
    localStorage.setItem('token', data.access_token)
    return data
  }

  function logout() {
    token.value = null
    localStorage.removeItem('token')
  }

  return { token, get, post, put, del, login, logout, request }
}
