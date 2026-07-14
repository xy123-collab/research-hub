<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const route = useRoute(); const router = useRouter()
const token = ref(''); const pw = ref(''); const pw2 = ref('')
const err = ref(''); const msg = ref('')

onMounted(() => { token.value = (route.query.token as string) || '' })

async function submit() {
  err.value = ''; msg.value = ''
  if (!token.value) { err.value = '缺少重置令牌，请从邮件链接进入'; return }
  if (pw.value.length < 6) { err.value = '新密码至少 6 位'; return }
  if (pw.value !== pw2.value) { err.value = '两次输入的密码不一致'; return }
  try {
    const r = await api.post('/auth/reset-password', { token: token.value, new_password: pw.value })
    msg.value = r.data.detail || '密码已重置'
    setTimeout(() => router.push('/login'), 1500)
  } catch (e: any) { err.value = e.response?.data?.detail || '重置失败' }
}
</script>
<template>
  <div class="min-h-screen flex flex-col items-center justify-center bg-paper px-6">
    <div class="card w-full max-w-sm">
      <h2 class="text-lg text-accent mb-3">重置密码</h2>
      <input v-model="pw" type="password" class="input mb-2" placeholder="新密码（至少 6 位）" />
      <input v-model="pw2" type="password" class="input mb-3" placeholder="确认新密码" @keyup.enter="submit" />
      <p v-if="err" class="text-accent2 text-xs mb-2">{{ err }}</p>
      <p v-if="msg" class="text-green-700 text-xs mb-2">{{ msg }}</p>
      <button class="btn-primary w-full" @click="submit">确认重置</button>
      <router-link to="/login" class="block text-center text-accent text-xs mt-3 hover:underline">← 返回登录</router-link>
    </div>
  </div>
</template>
