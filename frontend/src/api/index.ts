import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

function detailText(detail: any): string {
  if (typeof detail === 'string') return detail.trim()
  if (Array.isArray(detail)) {
    return detail.map((x: any) => {
      const field = Array.isArray(x?.loc) ? x.loc.filter((v: any) => v !== 'body').join('.') : ''
      return `${field ? field + '：' : ''}${x?.msg || String(x)}`
    }).join('；')
  }
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail)
  return ''
}

function actionOf(err: any): string {
  const cfg = err?.config || {}
  const url = String(cfg.url || '')
  const method = String(cfg.method || 'get').toLowerCase()
  if (cfg.responseType === 'blob' || /download|export|template|\/file(?:\?|$)/.test(url)) return '下载'
  if (method === 'delete') return '删除'
  if (method === 'patch' || method === 'put') return '保存'
  if (method === 'post' && (/upload|versions|attachments|candidate|literature\/parse|skills|entries/.test(url) || cfg.data instanceof FormData)) return '上传/提交'
  if (method === 'post') return '提交'
  return '加载'
}

export function apiErrorMessage(err: any, fallback = '操作失败'): string {
  const action = actionOf(err)
  const status = Number(err?.response?.status || 0)
  const detail = detailText(err?.response?.data?.detail) || detailText(err?.response?.data)
  let advice = ''
  if (!status) advice = '未连接到服务器；请检查网络，等待免费服务冷启动约 1 分钟后重试'
  else if (status === 401) advice = '登录已过期；请重新登录后再操作'
  else if (status === 403) advice = '当前账号权限不足；请先加入对应数据集/课题组，或申请该项单独授权'
  else if (status === 404 && action === '下载') advice = '文件或版本已不存在；若使用 Render 本地存储，可能因重启丢失，请管理员重新上传并检查 COS 配置'
  else if (status === 404) advice = '目标可能已被删除或页面信息已过期；请刷新页面后重试'
  else if (status === 409) advice = '内容已被其他操作更新；请刷新后核对最新状态'
  else if (status === 413 || /超过.*MB|过大/.test(detail)) advice = '请压缩或分拆文件，或联系管理员调整上传上限'
  else if (status === 422) advice = '表单字段不完整或格式不正确；请检查必填项、数字/日期格式和已选文件'
  else if (status === 429) advice = '请求过于频繁；请稍等片刻再试，不要连续点击提交'
  else if (status >= 500 && action === '下载') advice = '服务器未能读取存储文件；请管理员检查 COS/本地存储是否可用，并按当前版本重新上传'
  else if (status >= 500 && action === '上传/提交') advice = '服务器在解析或存储文件时失败；请检查文件未损坏、大小与格式合规，若重复发生请管理员检查存储配置'
  else if (status >= 500) advice = '服务器未能完成该操作；请记录操作位置与时间，刷新后重试，若重现请联系管理员查看服务日志'
  else if (/已存在|不可覆盖|重复/.test(detail)) advice = '请更换版本号/名称，或刷新后使用现有记录'
  else if (/文件|格式|解析|扩展名/.test(detail)) advice = '请确认文件未加密、未损坏，且扩展名与真实格式一致后重新选择'
  else if (status === 400) advice = '请按提示检查必填项、当前状态和输入格式后重试'
  const base = detail || `${fallback}（HTTP ${status || '无响应'}）`
  if (!advice || base.includes('建议：')) return base
  return `${base}。建议：${advice}`
}

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
    const message = apiErrorMessage(err)
    err.userMessage = message
    if (!err.response) {
      // 让现有各页的 e.response?.data?.detail 也能显示具体网络/冷启建议。
      err.response = { status: 0, data: { detail: message }, headers: {}, config: err.config }
    } else if (!(err.response.data instanceof Blob)) {
      if (!err.response.data || typeof err.response.data !== 'object') {
        err.response.data = { detail: message }
      } else {
        err.response.data.detail = message
      }
    }
    return Promise.reject(err)
  }
)

export default api
