<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import api from '../api'

const auth = useAuth()
const router = useRouter()
const mode = ref<'login' | 'register' | 'forgot'>('login')
const username = ref(''); const password = ref(''); const displayName = ref('')
const email = ref('')
const err = ref(''); const msg = ref(''); const cfg = ref<any>({})

onMounted(async () => { try { cfg.value = (await api.get('/config')).data } catch {} })

async function submit() {
  err.value = ''; msg.value = ''
  try {
    if (mode.value === 'login') {
      await auth.login(username.value, password.value)
      router.push('/')
    } else if (mode.value === 'register') {
      if (!email.value.trim()) { err.value = '注册必须填写邮箱（用于找回密码与消息通知）'; return }
      await auth.register({ username: username.value, password: password.value,
        display_name: displayName.value, email: email.value.trim() })
      router.push('/')
    } else {
      const r = await api.post('/auth/forgot-password', { email: email.value.trim() })
      msg.value = r.data.detail || '若该邮箱存在，我们已发送重置链接'
    }
  } catch (e: any) { err.value = e.response?.data?.detail || '失败' }
}
</script>
<template>
  <div class="min-h-screen flex flex-col items-center justify-center bg-paper px-6">
    <div class="text-center mb-6">
      <h1 class="text-2xl text-accent">{{ cfg.name_zh || '科研数据共享平台' }}</h1>
      <p class="text-gray-500 text-sm mt-1">{{ cfg.slogan_zh || '让每一份自建数据都可信、可迭代、可复用' }}</p>
    </div>
    <div class="card w-full max-w-sm">
      <div class="flex gap-2 mb-4 text-sm">
        <button :class="mode==='login'?'btn-primary':'btn-ghost'" @click="mode='login'">登录</button>
        <button :class="mode==='register'?'btn-primary':'btn-ghost'" @click="mode='register'">注册</button>
      </div>

      <template v-if="mode!=='forgot'">
        <input v-if="mode==='register'" v-model="displayName" class="input mb-2" placeholder="显示名" />
        <input v-model="username" class="input mb-2" placeholder="用户名" />
        <input v-if="mode==='register'" v-model="email" type="email" class="input mb-2" placeholder="邮箱（必填，用于找回密码）" />
        <input v-model="password" type="password" class="input mb-3" placeholder="密码" @keyup.enter="submit" />
      </template>
      <template v-else>
        <p class="text-sm text-gray-500 mb-2">输入注册邮箱，我们会给你发送重置密码的链接。</p>
        <input v-model="email" type="email" class="input mb-3" placeholder="注册邮箱" @keyup.enter="submit" />
      </template>

      <p v-if="err" class="text-accent2 text-xs mb-2">{{ err }}</p>
      <p v-if="msg" class="text-green-700 text-xs mb-2">{{ msg }}</p>
      <button class="btn-primary w-full" @click="submit">
        {{ mode==='login'?'登录':mode==='register'?'注册':'发送重置链接' }}
      </button>

      <div class="flex justify-between mt-3 text-[12px]">
        <button v-if="mode!=='forgot'" class="text-accent hover:underline" @click="mode='forgot';err='';msg=''">忘记密码？</button>
        <button v-else class="text-accent hover:underline" @click="mode='login';err='';msg=''">← 返回登录</button>
        <span class="text-gray-400">试用账号：lixiaoyu / pass123</span>
      </div>
    </div>
    <p class="text-xs text-gray-400 mt-8">北京大学国家发展研究院 · 智慧科研团队</p>
  </div>
</template>
