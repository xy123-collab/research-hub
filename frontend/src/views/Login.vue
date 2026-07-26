<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import api from '../api'

const auth = useAuth()
const router = useRouter()
const mode = ref<'login' | 'register' | 'forgot'>('login')
const forgotKind = ref<'password' | 'username'>('password')
const username = ref(''); const password = ref(''); const password2 = ref(''); const displayName = ref('')
const email = ref('')
const emailCode = ref(''); const inviteCode = ref('')
const err = ref(''); const msg = ref(''); const cfg = ref<any>({})
// 注册策略：由后台开关决定是否需要邀请码 / 邮箱验证码
const policy = ref<any>({ invite_required: false, email_verify_required: false,
  min_password_len: 10, code_ttl_minutes: 10 })
const sending = ref(false); const cooldown = ref(0)
let timer: any = null

onMounted(async () => {
  try { cfg.value = (await api.get('/config')).data } catch {}
  try { policy.value = (await api.get('/auth/register-policy')).data } catch {}
})
onUnmounted(() => { if (timer) clearInterval(timer) })

const pwHint = computed(() =>
  `密码至少 ${policy.value.min_password_len || 10} 位，且包含字母、数字、符号中的至少两类`)

async function sendCode() {
  err.value = ''; msg.value = ''
  if (!email.value.trim()) { err.value = '请先填写邮箱'; return }
  sending.value = true
  try {
    const r = await api.post('/auth/send-email-code', { email: email.value.trim() })
    msg.value = r.data.detail || '验证码已发送，请查收邮箱'
    cooldown.value = 60
    timer = setInterval(() => { if (--cooldown.value <= 0) clearInterval(timer) }, 1000)
  } catch (e: any) { err.value = e.response?.data?.detail || '发送失败' }
  finally { sending.value = false }
}

async function submit() {
  err.value = ''; msg.value = ''
  try {
    if (mode.value === 'login') {
      await auth.login(username.value, password.value)
      router.push('/')
    } else if (mode.value === 'register') {
      if (!email.value.trim()) { err.value = '注册必须填写邮箱（用于找回密码与消息通知）'; return }
      if (password.value !== password2.value) { err.value = '两次输入的密码不一致，请重新输入'; return }
      if (policy.value.email_verify_required && !emailCode.value.trim()) {
        err.value = '请先点击「发送验证码」并填写收到的邮箱验证码'; return }
      if (policy.value.invite_required && !inviteCode.value.trim()) {
        err.value = '当前为邀请制注册，请填写平台管理员发给你的邀请码'; return }
      await auth.register({ username: username.value, password: password.value,
        display_name: displayName.value, email: email.value.trim(),
        email_code: emailCode.value.trim() || null,
        invite_code: inviteCode.value.trim() || null })
      router.push('/')
    } else if (forgotKind.value === 'password') {
      const r = await api.post('/auth/forgot-password', { email: email.value.trim() })
      msg.value = r.data.detail || '若该邮箱存在，我们已发送重置链接'
    } else {
      const r = await api.post('/auth/forgot-username', { email: email.value.trim() })
      msg.value = r.data.detail || '若该邮箱存在，我们已发送你的账号名'
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
        <p v-if="mode==='register' && policy.invite_required"
           class="text-[11px] text-accent bg-paper border border-line rounded px-2 py-1.5 mb-2">
          本平台当前为<b>邀请制注册</b>：需要平台管理员发放的邀请码才能注册。
        </p>
        <input v-if="mode==='register'" v-model="displayName" class="input mb-2" placeholder="昵称（对外展示，之后可修改）" />
        <input v-model="username" class="input mb-1" placeholder="账号名" />
        <p v-if="mode==='register'" class="text-[11px] text-gray-400 mb-2">账号名用于登录，注册后不可修改，建议用字母/数字。</p>

        <template v-if="mode==='register'">
          <input v-model="email" type="email" class="input mb-2" placeholder="邮箱（必填，用于找回密码/账号名）" />
          <div v-if="policy.email_verify_required" class="flex gap-2 mb-2">
            <input v-model="emailCode" class="input flex-1" placeholder="邮箱验证码" />
            <button class="btn-ghost text-xs whitespace-nowrap px-3"
              :disabled="sending || cooldown>0" @click="sendCode">
              {{ cooldown>0 ? `${cooldown}s 后重发` : (sending ? '发送中…' : '发送验证码') }}
            </button>
          </div>
          <p v-if="policy.email_verify_required" class="text-[11px] text-gray-400 mb-2">
            验证码 {{ policy.code_ttl_minutes || 10 }} 分钟内有效；没收到请检查垃圾邮件。
          </p>
          <input v-if="policy.invite_required" v-model="inviteCode" class="input mb-2 uppercase"
            placeholder="邀请码（向平台管理员索取）" />
        </template>

        <input v-model="password" type="password" :class="mode==='register'?'input mb-1':'input mb-3'" placeholder="密码" @keyup.enter="mode==='login' && submit()" />
        <p v-if="mode==='register'" class="text-[11px] text-gray-400 mb-2">{{ pwHint }}</p>
        <input v-if="mode==='register'" v-model="password2" type="password" class="input mb-3" placeholder="再次输入密码（确认一致）" @keyup.enter="submit" />
      </template>
      <template v-else>
        <div class="flex gap-2 mb-3 text-xs">
          <button :class="forgotKind==='password'?'btn-primary':'btn-ghost'" @click="forgotKind='password';err='';msg=''">找回密码</button>
          <button :class="forgotKind==='username'?'btn-primary':'btn-ghost'" @click="forgotKind='username';err='';msg=''">找回账号名</button>
        </div>
        <p class="text-sm text-gray-500 mb-2">
          {{ forgotKind==='password' ? '输入注册邮箱，我们会给你发送重置密码的链接。' : '输入注册邮箱，我们会把该邮箱对应的账号名发送给你。' }}
        </p>
        <input v-model="email" type="email" class="input mb-3" placeholder="注册邮箱" @keyup.enter="submit" />
      </template>

      <p v-if="err" class="text-accent2 text-xs mb-2">{{ err }}</p>
      <p v-if="msg" class="text-green-700 text-xs mb-2">{{ msg }}</p>
      <button class="btn-primary w-full" @click="submit">
        {{ mode==='login'?'登录':mode==='register'?'注册':(forgotKind==='password'?'发送重置链接':'发送账号名') }}
      </button>

      <div class="flex justify-between mt-3 text-[12px]">
        <button v-if="mode!=='forgot'" class="text-accent hover:underline" @click="mode='forgot';forgotKind='password';err='';msg=''">忘记密码 / 账号名？</button>
        <button v-else class="text-accent hover:underline" @click="mode='login';err='';msg=''">← 返回登录</button>
      </div>
    </div>
    <p class="text-xs text-gray-400 mt-8">北京大学国家发展研究院 · 智慧科研团队</p>
  </div>
</template>
