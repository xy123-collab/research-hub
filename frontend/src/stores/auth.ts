import { defineStore } from 'pinia'
import api from '../api'

export const useAuth = defineStore('auth', {
  state: () => ({ user: null as any, loaded: false }),
  actions: {
    async login(username: string, password: string) {
      const { data } = await api.post('/auth/login', { username, password })
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      await this.fetchMe()
    },
    async register(payload: any) {
      const { data } = await api.post('/auth/register', payload)
      localStorage.setItem('access_token', data.access_token)
      // 注册也要存 refresh_token，否则新用户满一小时就掉线（A1）
      localStorage.setItem('refresh_token', data.refresh_token)
      await this.fetchMe()
    },
    async fetchMe() {
      try { this.user = (await api.get('/me')).data } catch { this.user = null }
      this.loaded = true
    },
    async logout() {
      // 通知后端把这条 refresh_token 作废，避免登出后令牌仍在有效期内可用
      const rt = localStorage.getItem('refresh_token')
      try { await api.post('/auth/logout', { refresh_token: rt || '' }) } catch {}
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      this.user = null
      location.hash = '#/login'
    }
  }
})
