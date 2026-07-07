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
      await this.fetchMe()
    },
    async fetchMe() {
      try { this.user = (await api.get('/me')).data } catch { this.user = null }
      this.loaded = true
    },
    logout() {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      this.user = null
      location.hash = '#/login'
    }
  }
})
