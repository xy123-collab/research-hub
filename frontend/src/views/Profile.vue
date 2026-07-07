<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuth } from '../stores/auth'
import api from '../api'

const route = useRoute(); const { t } = useI18n(); const auth = useAuth()
const uid = ref<number>(0)
const profile = ref<any>(null); const tab = ref('projects')
const projects = ref<any[]>([]); const contrib = ref<any>({ total: 0, events: [] })
const resume = ref<any>({ blocks: [] }); const workspaces = ref<any[]>([])
const isMe = ref(false)
const newBlock = ref({ type: 'p', text_zh: '' })

onMounted(load)
watch(() => route.params.id, load)
async function load() {
  await auth.fetchMe()
  uid.value = route.params.id ? +route.params.id : auth.user?.id
  isMe.value = uid.value === auth.user?.id
  profile.value = (await api.get(`/users/${uid.value}`)).data
  projects.value = (await api.get('/projects', { params: { author_id: uid.value } })).data
  resume.value = (await api.get(`/users/${uid.value}/resume`)).data
  if (isMe.value) {
    contrib.value = (await api.get('/me/contributions')).data
    workspaces.value = (await api.get('/workspaces')).data
  }
}
async function addBlock() {
  await api.put('/me/resume'); await api.post('/me/resume/blocks', { ...newBlock.value, seq: resume.value.blocks.length })
  newBlock.value = { type: 'p', text_zh: '' }; resume.value = (await api.get(`/users/${uid.value}/resume`)).data
}
async function delBlock(id: number) { await api.delete(`/me/resume/blocks/${id}`); resume.value = (await api.get(`/users/${uid.value}/resume`)).data }
</script>
<template>
  <div v-if="profile">
    <div class="rounded-lg p-6 text-white" style="background: linear-gradient(135deg,#2d4a7c,#3d5a8c)">
      <div class="flex items-center gap-4">
        <div class="w-16 h-16 rounded-full bg-white/20 flex items-center justify-center text-2xl">👤</div>
        <div>
          <h1 class="text-2xl font-serif">{{ profile.display_name }}</h1>
          <p class="text-white/80 text-sm">{{ profile.bio_zh }}</p>
        </div>
        <div class="ml-auto text-right">
          <div class="text-3xl font-serif">{{ profile.contribution }}</div>
          <div class="label-cap text-white/70">{{ t('profile.contribution') }}</div>
        </div>
      </div>
    </div>

    <div class="flex gap-1 border-b border-line mt-5 text-sm">
      <button v-for="[k,l] in [['projects','profile.projects'],['contrib','profile.myContrib'],['resume','profile.resume'],['ws','项目工作台']]"
        :key="k" @click="tab=k as string" :class="['px-3 py-2', tab===k?'border-b-2 border-accent text-accent':'text-gray-500']">
        {{ typeof l === 'string' && l.includes('.') ? t(l) : l }}
      </button>
    </div>

    <div class="py-5">
      <div v-if="tab==='projects'" class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div v-for="p in projects" :key="p.id" class="card">
          <h3>{{ p.title }} <span class="tag ml-1">{{ p.status }}</span></h3>
          <p class="text-sm text-gray-500 mt-1">{{ p.body_zh }}</p>
        </div>
        <p v-if="!projects.length" class="text-gray-400 text-sm">暂无项目。</p>
      </div>

      <div v-else-if="tab==='contrib'">
        <div class="card">
          <div class="label-cap">总贡献度 {{ contrib.total }}</div>
          <table class="w-full text-sm mt-2">
            <tr v-for="(e,i) in contrib.events" :key="i" class="border-t border-line">
              <td class="py-1"><span class="tag">{{ e.type }}</span></td>
              <td>{{ e.ref_type }} #{{ e.ref_id }}</td>
              <td class="text-right font-mono">+{{ e.weight }}</td>
            </tr>
          </table>
          <p v-if="!contrib.events.length" class="text-gray-400 text-sm mt-2">暂无贡献记录。</p>
        </div>
      </div>

      <div v-else-if="tab==='resume'">
        <div v-for="b in resume.blocks" :key="b.id" class="mb-2 flex items-start gap-2">
          <component :is="b.type==='h'?'h2':b.type==='h2'?'h3':'p'" class="flex-1"
            :class="b.type==='li'?'pl-4 list-item':''">{{ b.text_zh }}</component>
          <button v-if="isMe" class="text-xs text-accent2" @click="delBlock(b.id)">×</button>
        </div>
        <div v-if="isMe" class="card mt-3">
          <div class="flex gap-2">
            <select v-model="newBlock.type" class="input w-32">
              <option value="h">大标题</option><option value="h2">小标题</option>
              <option value="p">正文</option><option value="li">分点</option>
            </select>
            <input v-model="newBlock.text_zh" class="input" placeholder="内容" @keyup.enter="addBlock" />
            <button class="btn-primary" @click="addBlock">＋</button>
          </div>
        </div>
        <p v-if="!resume.blocks.length && !isMe" class="text-gray-400 text-sm">暂无简历。</p>
      </div>

      <div v-else-if="tab==='ws'">
        <div v-for="w in workspaces" :key="w.id" class="card mb-2 flex items-center justify-between">
          <span>{{ w.title }}</span>
          <a v-if="w.overleaf_url" :href="w.overleaf_url" target="_blank" class="text-accent text-xs">Overleaf ↗</a>
        </div>
        <p v-if="!workspaces.length" class="text-gray-400 text-sm">暂无项目工作台（私密协作）。</p>
      </div>
    </div>
  </div>
</template>
