import api, { apiErrorMessage } from '../api'

// 带鉴权的文件下载：window.open 不会带 Authorization 头，导致需要登录的
// 下载接口（模板/导出/附件等）返回 401。这里用 axios 以 blob 拉取（拦截器会
// 自动加 Bearer token），再在浏览器触发下载。
export async function downloadFile(url: string, fallbackName = 'download') {
  try {
    const resp = await api.get(url, { responseType: 'blob' })
    // 从响应头解析文件名
    let name = fallbackName
    const cd = resp.headers['content-disposition'] || ''
    const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd)
    if (m) name = decodeURIComponent(m[1])
    const blob = new Blob([resp.data])
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = name
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  } catch (e: any) {
    // blob 错误响应需要读回文本
    try {
      if (e.response?.data instanceof Blob) e.response.data = JSON.parse(await e.response.data.text())
    } catch {}
    alert(apiErrorMessage(e, '下载失败'))
  }
}
