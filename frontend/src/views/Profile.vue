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

// ---------- 项目工作台 ----------
const showWsCreate = ref(false)
const wsForm = ref<any>({ title: '', overleaf_url: '' })
const wsModal = ref<any>(null)
const wsInput = ref<any>({ update: '', todo: '', note: '' })
const wsFile = ref<File | null>(null)
async function reloadWs() { workspaces.value = (await api.get('/workspaces')).data }
async function createWs() {
  try {
    await api.post('/workspaces', { title: wsForm.value.title, overleaf_url: wsForm.value.overleaf_url || null, member_ids: [] })
    showWsCreate.value = false; wsForm.value = { title: '', overleaf_url: '' }; reloadWs()
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function openWs(id: number) { wsModal.value = (await api.get(`/workspaces/${id}`)).data }
async function addUpdate() { await api.post(`/workspaces/${wsModal.value.id}/updates`, { body: wsInput.value.update }); wsInput.value.update=''; openWs(wsModal.value.id) }
async function addTodo() { await api.post(`/workspaces/${wsModal.value.id}/todos`, { text: wsInput.value.todo }); wsInput.value.todo=''; openWs(wsModal.value.id) }
async function toggleTodo(t: any) { await api.patch(`/workspaces/${wsModal.value.id}/todos/${t.id}`, { done: !t.done }); openWs(wsModal.value.id) }
async function addNote() { await api.post(`/workspaces/${wsModal.value.id}/notes`, { body: wsInput.value.note }); wsInput.value.note=''; openWs(wsModal.value.id) }
async function uploadWsFile() {
  if (!wsFile.value) return
  const fd = new FormData(); fd.append('file', wsFile.value)
  await api.post(`/workspaces/${wsModal.value.id}/files`, fd); wsFile.value = null; openWs(wsModal.value.id)
}
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
        <div v-if="isMe" class="mb-3"><button class="btn-primary" @click="showWsCreate=true">＋新建工作台</button></div>
        <div v-for="w in workspaces" :key="w.id" class="card mb-2 flex items-center justify-between cursor-pointer" @click="openWs(w.id)">
          <span>{{ w.title }} <span v-if="w.is_owner" class="tag ml-1">owner</span></span>
          <a v-if="w.overleaf_url" :href="w.overleaf_url" target="_blank" class="text-accent text-xs" @click.stop>Overleaf ↗</a>
        </div>
        <p v-if="!workspaces.length" class="text-gray-400 text-sm">暂无项目工作台（私密协作，仅选定成员可见）。</p>
      </div>
    </div>

    <!-- 新建工作台 -->
    <div v-if="showWsCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showWsCreate=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-3">新建项目工作台</h3>
        <input v-model="wsForm.title" class="input mb-2" placeholder="标题" />
        <input v-model="wsForm.overleaf_url" class="input mb-3" placeholder="Overleaf 链接（https://www.overleaf.com/...，可选）" />
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showWsCreate=false">取消</button>
          <button class="btn-primary" @click="createWs">创建</button>
        </div>
      </div>
    </div>

    <!-- 工作台详情 -->
    <div v-if="wsModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="wsModal=null">
      <div class="bg-white rounded-lg max-w-2xl w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <div class="flex items-center justify-between">
          <h3 class="text-lg">{{ wsModal.title }}</h3>
          <button @click="wsModal=null" class="text-gray-400">×</button>
        </div>
        <a v-if="wsModal.overleaf_url" :href="wsModal.overleaf_url" target="_blank" class="text-accent text-xs">Overleaf ↗</a>

        <div class="grid md:grid-cols-2 gap-4 mt-4">
          <div>
            <div class="label-cap mb-1">进展记录</div>
            <div class="flex gap-2 mb-2">
              <input v-model="wsInput.update" class="input" placeholder="＋更新进展" @keyup.enter="addUpdate" />
              <button class="btn-ghost text-xs" @click="addUpdate">加</button>
            </div>
            <div v-for="u in wsModal.updates" :key="u.id" class="text-sm border-t border-line py-1">{{ u.body }}</div>
          </div>
          <div>
            <div class="label-cap mb-1">待办</div>
            <div class="flex gap-2 mb-2">
              <input v-model="wsInput.todo" class="input" placeholder="＋新增待办" @keyup.enter="addTodo" />
              <button class="btn-ghost text-xs" @click="addTodo">加</button>
            </div>
            <label v-for="t in wsModal.todos" :key="t.id" class="flex items-center gap-2 text-sm py-1">
              <input type="checkbox" :checked="t.done" @change="toggleTodo(t)" />
              <span :class="t.done?'line-through text-gray-400':''">{{ t.text }}</span>
            </label>
          </div>
          <div>
            <div class="label-cap mb-1">讨论/结果存档</div>
            <div class="flex gap-2 mb-2">
              <input v-model="wsInput.note" class="input" placeholder="＋新增讨论" @keyup.enter="addNote" />
              <button class="btn-ghost text-xs" @click="addNote">加</button>
            </div>
            <div v-for="n in wsModal.notes" :key="n.id" class="text-sm border-t border-line py-1">{{ n.body }}</div>
          </div>
          <div>
            <div class="label-cap mb-1">结果文件</div>
            <div class="flex gap-2 mb-2">
              <input type="file" @change="(e:any)=>wsFile=e.target.files[0]" class="text-xs" />
              <button class="btn-ghost text-xs" @click="uploadWsFile">上传</button>
            </div>
            <a v-for="f in wsModal.files" :key="f.id" :href="`/api/workspaces/${wsModal.id}/files/${f.id}/download`" target="_blank" class="text-accent text-xs block hover:underline">📎 {{ f.file_name }}</a>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
