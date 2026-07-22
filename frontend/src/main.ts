import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import i18n from './i18n'
import App from './App.vue'
import './style.css'

// 少数旧页面的保存/编辑函数没有单独 catch；统一兜底显示 API 已生成的
// 「具体原因 + 改正建议」，避免点击后没有反馈。
window.addEventListener('unhandledrejection', (event) => {
  const message = event.reason?.userMessage
  if (message) {
    event.preventDefault()
    alert(message)
  }
})

createApp(App).use(createPinia()).use(router).use(i18n).mount('#app')
