<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuth } from '../stores/auth'
import api from '../api'
import Icon from '../components/Icon.vue'
import ScopeSelector from '../components/ScopeSelector.vue'

const { t } = useI18n(); const auth = useAuth()
const posts = ref<any[]>([])
const form = ref({ content_zh: '', tags: '' })
const scope = ref<{ scope: string; scope_ref_id: number | null }>({ scope: 'public', scope_ref_id: null })

// 评论区状态：postId -> {open, list, input, replyTo}
const cstate = ref<Record<number, any>>({})

onMounted(load)
async function load() { posts.value = (await api.get('/posts')).data }
async function submit() {
  if (!form.value.content_zh) return
  if ((scope.value.scope === 'group' || scope.value.scope === 'dataset') && !scope.value.scope_ref_id) {
    alert('请在下拉框中选择具体的课题组/数据集'); return
  }
  try {
    await api.post('/posts', { content_zh: form.value.content_zh,
      scope: scope.value.scope, scope_ref_id: scope.value.scope_ref_id,
      tags: form.value.tags ? form.value.tags.split(',').map(s=>s.trim()) : [] })
    form.value = { content_zh: '', tags: '' }; scope.value = { scope: 'public', scope_ref_id: null }
    load()
  } catch (e: any) { alert(e.response?.data?.detail || '发布失败') }
}
async function like(p: any) { await api.post(`/posts/${p.id}/react`, null, { params: { type: 'like' } }); load() }

async function toggleComments(p: any) {
  if (cstate.value[p.id]?.open) { cstate.value[p.id].open = false; return }
  cstate.value[p.id] = { open: true, list: [], input: '', replyTo: null }
  await loadComments(p.id)
}
async function loadComments(pid: number) {
  cstate.value[pid].list = (await api.get(`/posts/${pid}/comments`)).data
}
function topComments(pid: number) { return (cstate.value[pid]?.list || []).filter((c: any) => !c.parent_id) }
function replies(pid: number, id: number) { return (cstate.value[pid]?.list || []).filter((c: any) => c.parent_id === id) }
async function sendComment(pid: number) {
  const s = cstate.value[pid]
  if (!s.input.trim()) return
  await api.post(`/posts/${pid}/comments`, { content: s.input.trim(), parent_id: s.replyTo?.id || null })
  s.input = ''; s.replyTo = null; loadComments(pid)
}
async function delComment(pid: number, c: any) {
  if (!confirm('删除该评论？')) return
  await api.delete(`/comments/${c.id}`); loadComments(pid)
}
</script>
<template>
  <h1 class="text-2xl mb-4">{{ t('nav.feed') }}</h1>
  <div class="card mb-6">
    <textarea v-model="form.content_zh" class="input" placeholder="分享一个研究想法 / 发起一段讨论…"></textarea>
    <div class="grid md:grid-cols-2 gap-2 mt-2">
      <ScopeSelector v-model="scope" />
      <div>
        <label class="label-cap">标签</label>
        <input v-model="form.tags" class="input" placeholder="标签（逗号分隔，如 COD）" />
      </div>
    </div>
    <div class="flex justify-end mt-2"><button class="btn-primary" @click="submit">{{ t('feed.post') }}</button></div>
  </div>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div v-for="p in posts" :key="p.id" class="card">
      <div class="flex items-center gap-2 text-sm">
        <Icon name="bulb" class="ico text-accent" />
        <router-link :to="`/users/${p.author_id}`" class="text-accent hover:underline">{{ p.author_name }}</router-link>
        <span class="tag ml-auto">{{ p.scope_label || p.visibility }}</span>
      </div>
      <p class="mt-2 text-sm">{{ p.content_zh }}</p>
      <div class="mt-2 flex items-center gap-2">
        <span v-for="tag in p.tags" :key="tag" class="tag">{{ tag }}</span>
        <button class="text-xs text-gray-500 ml-auto hover:text-accent" @click="toggleComments(p)">
          评论{{ cstate[p.id]?.open ? ' ▲' : ' ▼' }}</button>
        <button class="text-xs text-gray-500 hover:text-accent" @click="like(p)">♥ {{ p.likes }}</button>
      </div>

      <!-- 评论区（含评论的评论）-->
      <div v-if="cstate[p.id]?.open" class="mt-3 border-t border-line pt-3">
        <div v-for="c in topComments(p.id)" :key="c.id" class="mb-2.5">
          <div class="text-sm"><span class="text-accent">{{ c.user_name }}</span>
            <span class="text-gray-400 text-xs ml-2">{{ (c.created_at||'').slice(0,16).replace('T',' ') }}</span></div>
          <p class="text-sm text-gray-700">{{ c.content }}</p>
          <div class="flex gap-2 text-xs mt-0.5">
            <button class="text-gray-500 hover:text-accent" @click="cstate[p.id].replyTo=c">回复</button>
            <button v-if="c.user_id===auth.user?.id" class="text-gray-400 hover:text-accent2" @click="delComment(p.id,c)">删除</button>
          </div>
          <!-- 回复列表 -->
          <div v-for="r in replies(p.id, c.id)" :key="r.id" class="ml-4 mt-1.5 pl-3 border-l-2 border-line">
            <div class="text-sm"><span class="text-accent">{{ r.user_name }}</span>
              <span class="text-gray-400 text-xs ml-2">{{ (r.created_at||'').slice(0,16).replace('T',' ') }}</span></div>
            <p class="text-sm text-gray-700">{{ r.content }}</p>
            <button v-if="r.user_id===auth.user?.id" class="text-gray-400 hover:text-accent2 text-xs" @click="delComment(p.id,r)">删除</button>
          </div>
        </div>
        <p v-if="!topComments(p.id).length" class="text-gray-400 text-xs mb-2">还没有评论，来说两句。</p>

        <div v-if="cstate[p.id].replyTo" class="text-xs text-gray-500 mb-1">回复 @{{ cstate[p.id].replyTo.user_name }}
          <button class="text-accent2 ml-1" @click="cstate[p.id].replyTo=null">取消</button></div>
        <div class="flex gap-2">
          <input v-model="cstate[p.id].input" class="input text-sm" placeholder="写评论…" @keyup.enter="sendComment(p.id)" />
          <button class="btn-primary text-sm" @click="sendComment(p.id)">发送</button>
        </div>
      </div>
    </div>
  </div>
</template>
