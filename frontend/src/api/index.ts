import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem('access_token')
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && !location.hash.includes('/login')) {
      localStorage.removeItem('access_token')
      location.hash = '#/login'
    }
    return Promise.reject(err)
  }
)

export default api
