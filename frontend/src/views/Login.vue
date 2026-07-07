<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import api from '../api'

const auth = useAuth()
const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const username = ref(''); const password = ref(''); const displayName = ref('')
const err = ref(''); const cfg = ref<any>({})

onMounted(async () => { try { cfg.value = (await api.get('/config')).data } catch {} })

async function submit() {
  err.value = ''
  try {
    if (mode.value === 'login') await auth.login(username.value, password.value)
    else await auth.register({ username: username.value, password: password.value, display_name: displayName.value })
    router.push('/')
  } catch (e: any) { err.value = e.response?.data?.detail || '失败' }
}
</script>
<template>
  <div class="min-h-screen flex flex-col items-center justify-center bg-paper px-6">
    <div class="text-center mb-6">
      <h1 class="text-2xl text-accent">{{ cfg.name_zh || '科研数据共享平台' }}</h1>
      <p class="text-gray-500 text-sm mt-1">{{ cfg.slogan_zh || '让每一份自建数据都可信、可复用、可归属' }}</p>
    </div>
    <div class="card w-full max-w-sm">
      <div class="flex gap-2 mb-4 text-sm">
        <button :class="mode==='login'?'btn-primary':'btn-ghost'" @click="mode='login'">登录</button>
        <button :class="mode==='register'?'btn-primary':'btn-ghost'" @click="mode='register'">注册</button>
      </div>
      <input v-if="mode==='register'" v-model="displayName" class="input mb-2" placeholder="显示名" />
      <input v-model="username" class="input mb-2" placeholder="用户名" />
      <input v-model="password" type="password" class="input mb-3" placeholder="密码" @keyup.enter="submit" />
      <p v-if="err" class="text-accent2 text-xs mb-2">{{ err }}</p>
      <button class="btn-primary w-full" @click="submit">{{ mode==='login'?'登录':'注册' }}</button>
      <p class="text-[11px] text-gray-400 mt-3">试用账号：lixiaoyu / pass123</p>
    </div>
    <p class="text-xs text-gray-400 mt-8">北京大学国家发展研究院 · 智慧科研团队</p>
  </div>
</template>
