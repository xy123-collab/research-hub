<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuth } from '../stores/auth'
import api from '../api'
import Icon from '../components/Icon.vue'
import ScopeSelector from '../components/ScopeSelector.vue'

const route = useRoute(); const { t } = useI18n(); const auth = useAuth()
const uid = ref<number>(0)
const profile = ref<any>(null); const tab = ref('projects')
const projects = ref<any[]>([]); const contrib = ref<any>({ total: 0, events: [] })
const resume = ref<any>({ blocks: [] }); const workspaces = ref<any[]>([])
const isMe = ref(false)

onMounted(load)
watch(() => route.params.id, load)
watch(() => route.query.tab, (v) => { if (v) tab.value = String(v) })
async function load() {
  await auth.fetchMe()
  uid.value = route.params.id ? +route.params.id : auth.user?.id
  isMe.value = uid.value === auth.user?.id
  profile.value = (await api.get(`/users/${uid.value}`)).data
  projects.value = (await api.get('/projects', { params: { author_id: uid.value } })).data
  resume.value = (await api.get(`/users/${uid.value}/resume`)).data
  if (route.query.tab) tab.value = String(route.query.tab)
  if (isMe.value) {
    contrib.value = (await api.get('/me/contributions')).data
    workspaces.value = (await api.get('/workspaces')).data
  }
}

// ==================== 编辑资料 ====================
const showEdit = ref(false)
const editForm = ref<any>({ display_name: '', research_direction: '', keywords: '', avatar: '' })
const editSnapshot = ref('')
const avatarFile = ref<File | null>(null); const avatarPreview = ref('')
const saving = ref(false)
const dirty = computed(() => JSON.stringify(editForm.value) !== editSnapshot.value || !!avatarFile.value)

function openEdit() {
  editForm.value = {
    display_name: profile.value.display_name || '',
    research_direction: profile.value.research_direction || '',
    keywords: profile.value.keywords || '',
    avatar: profile.value.avatar || ''
  }
  editSnapshot.value = JSON.stringify(editForm.value)
  avatarFile.value = null; avatarPreview.value = ''
  showEdit.value = true
}
function pickAvatar(e: any) {
  const f = e.target.files?.[0]; if (!f) return
  avatarFile.value = f; avatarPreview.value = URL.createObjectURL(f)
}
function closeEdit() {
  if (dirty.value && !confirm('有未保存的修改，确定放弃吗？')) return
  showEdit.value = false
}
async function saveEdit() {
  saving.value = true
  try {
    if (avatarFile.value) {
      const fd = new FormData(); fd.append('file', avatarFile.value)
      const r = await api.post('/me/avatar', fd)
      editForm.value.avatar = r.data.avatar
    }
    await api.patch('/me', {
      display_name: editForm.value.display_name,
      research_direction: editForm.value.research_direction,
      keywords: editForm.value.keywords
    })
    await auth.fetchMe()
    profile.value = (await api.get(`/users/${uid.value}`)).data
    editSnapshot.value = JSON.stringify(editForm.value); avatarFile.value = null
    showEdit.value = false
  } catch (e: any) { alert(e.response?.data?.detail || '保存失败') }
  finally { saving.value = false }
}

const keywordList = computed(() =>
  (profile.value?.keywords || '').split(/[,，、]/).map((s: string) => s.trim()).filter(Boolean))

// ==================== 简历（整块编辑，更快）====================
// 用一个文本框编辑整份简历：# 大标题 / ## 小标题 / - 分点 / 其余为正文
const showResumeEdit = ref(false)
const resumeText = ref(''); const resumeSnapshot = ref('')
const resumeDirty = computed(() => resumeText.value !== resumeSnapshot.value)
function blocksToText(blocks: any[]) {
  return blocks.map(b => {
    if (b.type === 'h') return '# ' + (b.text_zh || '')
    if (b.type === 'h2') return '## ' + (b.text_zh || '')
    if (b.type === 'li') return '- ' + (b.text_zh || '')
    return b.text_zh || ''
  }).join('\n')
}
function textToBlocks(text: string) {
  return text.split('\n').map(line => {
    const l = line.trim()
    if (!l) return null
    if (l.startsWith('## ')) return { type: 'h2', text_zh: l.slice(3).trim() }
    if (l.startsWith('# ')) return { type: 'h', text_zh: l.slice(2).trim() }
    if (l.startsWith('- ') || l.startsWith('· ')) return { type: 'li', text_zh: l.slice(2).trim() }
    return { type: 'p', text_zh: l }
  }).filter(Boolean)
}
function openResumeEdit() {
  resumeText.value = blocksToText(resume.value.blocks)
  resumeSnapshot.value = resumeText.value
  showResumeEdit.value = true
}
function closeResumeEdit() {
  if (resumeDirty.value && !confirm('有未保存的修改，确定放弃吗？')) return
  showResumeEdit.value = false
}
async function saveResume() {
  try {
    await api.put('/me/resume/blocks', { blocks: textToBlocks(resumeText.value) })
    resume.value = (await api.get(`/users/${uid.value}/resume`)).data
    resumeSnapshot.value = resumeText.value
    showResumeEdit.value = false
  } catch (e: any) { alert(e.response?.data?.detail || '保存失败') }
}

// ==================== 在做项目：创建 + 置顶 ====================
const showProjCreate = ref(false)
const projForm = ref<any>({ title: '', body_zh: '', pinned: false })
const projScope = ref<{ scope: string; scope_ref_ids: number[] }>({ scope: 'public', scope_ref_ids: [] })
const projImage = ref<File | null>(null); const projImgPreview = ref('')
function pickProjImage(e: any) {
  const f = e.target.files?.[0]; if (!f) return
  projImage.value = f; projImgPreview.value = URL.createObjectURL(f)
}
function openProjCreate() {
  projForm.value = { title: '', body_zh: '', pinned: false }
  projScope.value = { scope: 'public', scope_ref_ids: [] }
  projImage.value = null; projImgPreview.value = ''; showProjCreate.value = true
}
async function createProject() {
  if (!projForm.value.title.trim() || !projForm.value.body_zh.trim() || !projImage.value) {
    alert('标题、图片、文字均为必填'); return
  }
  if ((projScope.value.scope === 'group' || projScope.value.scope === 'dataset') && !projScope.value.scope_ref_ids.length) {
    alert('请勾选至少一个课题组/数据集'); return
  }
  const fd = new FormData()
  fd.append('title', projForm.value.title.trim())
  fd.append('body_zh', projForm.value.body_zh.trim())
  fd.append('pinned', String(projForm.value.pinned))
  fd.append('scope', projScope.value.scope)
  if (projScope.value.scope_ref_ids.length) fd.append('scope_ref_ids', projScope.value.scope_ref_ids.join(','))
  fd.append('image', projImage.value)
  try {
    await api.post('/projects', fd)
    showProjCreate.value = false
    projects.value = (await api.get('/projects', { params: { author_id: uid.value } })).data
  } catch (e: any) { alert(e.response?.data?.detail || '创建失败') }
}
async function togglePin(p: any) {
  try {
    await api.post(`/projects/${p.id}/pin`, null, { params: { pinned: !p.pinned } })
    projects.value = (await api.get('/projects', { params: { author_id: uid.value } })).data
  } catch (e: any) { alert(e.response?.data?.detail || '操作失败') }
}

// ==================== 项目工作台 ====================
const showWsCreate = ref(false)
const wsForm = ref<any>({ title: '', overleaf_url: '' })
const wsInvited = ref<any[]>([])          // 已选邀请成员 {id,name}
const wsModal = ref<any>(null)
const entryCat = ref('all')
const entryForm = ref<any>({ category: 'progress', title: '', body: '' })
const entryFile = ref<File | null>(null)

const CATS: Record<string, string> = {
  progress: '进展', data: '数据', figure: '图表', literature: '文献',
  result: '结果', discussion: '讨论', other: '其他'
}

// 成员检索（按姓名/ID）
const memberQ = ref(''); const memberResults = ref<any[]>([])
async function searchMembers() {
  const q = memberQ.value.trim()
  memberResults.value = (await api.get('/users/search', { params: { q } })).data
    .filter((u: any) => u.id !== auth.user?.id)
}
function inviteMember(u: any) {
  if (wsInvited.value.find(x => x.id === u.id)) return
  wsInvited.value.push({ id: u.id, name: u.display_name })
}
function removeInvited(id: number) { wsInvited.value = wsInvited.value.filter(x => x.id !== id) }

async function reloadWs() { workspaces.value = (await api.get('/workspaces')).data }
function openWsCreate() {
  wsForm.value = { title: '', overleaf_url: '' }; wsInvited.value = []
  memberQ.value = ''; memberResults.value = []; showWsCreate.value = true
}
async function createWs() {
  if (!wsForm.value.title.trim()) { alert('请填写工作台标题'); return }
  try {
    await api.post('/workspaces', {
      title: wsForm.value.title.trim(),
      overleaf_url: wsForm.value.overleaf_url || null,
      member_ids: wsInvited.value.map(x => x.id)
    })
    showWsCreate.value = false; reloadWs()
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function openWs(id: number) { wsModal.value = (await api.get(`/workspaces/${id}`)).data; entryCat.value = 'all' }
async function delWs(id: number) {
  if (!confirm('确定删除该工作台？')) return
  await api.delete(`/workspaces/${id}`); reloadWs()
}
const filteredEntries = computed(() => {
  const es = wsModal.value?.entries || []
  return entryCat.value === 'all' ? es : es.filter((e: any) => e.category === entryCat.value)
})
const entryCatCounts = computed(() => {
  const m: Record<string, number> = {}
  for (const e of (wsModal.value?.entries || [])) m[e.category] = (m[e.category] || 0) + 1
  return m
})
async function addEntry() {
  if (!entryForm.value.body.trim() && !entryForm.value.title.trim() && !entryFile.value) {
    alert('请至少填写文字或选择文件'); return
  }
  const fd = new FormData()
  fd.append('category', entryForm.value.category)
  fd.append('title', entryForm.value.title)
  fd.append('body', entryForm.value.body)
  if (entryFile.value) fd.append('file', entryFile.value)
  await api.post(`/workspaces/${wsModal.value.id}/entries`, fd)
  entryForm.value = { category: entryForm.value.category, title: '', body: '' }
  entryFile.value = null
  openWs(wsModal.value.id)
}
async function delEntry(eid: number) {
  if (!confirm('删除这条记录？')) return
  await api.delete(`/workspaces/${wsModal.value.id}/entries/${eid}`); openWs(wsModal.value.id)
}
</script>
<template>
  <div v-if="profile">
    <!-- 顶部资料卡 -->
    <div class="rounded-lg p-6 text-white relative" style="background: linear-gradient(135deg,#2d4a7c,#3d5a8c)">
      <button v-if="isMe" class="absolute top-4 right-4 text-xs bg-white/15 hover:bg-white/25 rounded px-3 py-1.5"
        @click="openEdit">编辑资料</button>
      <div class="flex items-center gap-4">
        <div class="w-16 h-16 rounded-full bg-white/20 flex items-center justify-center overflow-hidden">
          <img v-if="profile.avatar" :src="profile.avatar" class="w-full h-full object-cover" />
          <Icon v-else name="users" class="ico" style="width:26px;height:26px" />
        </div>
        <div>
          <h1 class="text-2xl font-serif">{{ profile.display_name }}
            <span class="text-white/50 text-sm font-sans">ID {{ profile.id }}</span></h1>
          <p v-if="profile.research_direction" class="text-white/85 text-sm mt-0.5">
            研究方向：{{ profile.research_direction }}</p>
          <div v-if="keywordList.length" class="flex flex-wrap gap-1 mt-1.5">
            <span v-for="k in keywordList" :key="k" class="text-[11px] bg-white/15 rounded px-2 py-0.5">{{ k }}</span>
          </div>
        </div>
        <div class="ml-auto text-right self-start">
          <div class="text-3xl font-serif">{{ profile.contribution }}</div>
          <div class="label-cap text-white/70">{{ t('profile.contribution') }}</div>
        </div>
      </div>
    </div>

    <div class="flex gap-1 border-b border-line mt-5 text-sm">
      <button v-for="[k,l] in [['projects','在做的项目'],['contrib','我的贡献'],['resume','个人简历'],['ws','项目工作台']]"
        :key="k" @click="tab=k as string" :class="['px-3 py-2', tab===k?'border-b-2 border-accent text-accent':'text-gray-500']">
        {{ l }}
      </button>
    </div>

    <div class="py-5">
      <!-- 在做的项目 -->
      <div v-if="tab==='projects'">
        <div v-if="isMe" class="mb-3"><button class="btn-primary" @click="openProjCreate">＋创建项目</button></div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div v-for="p in projects" :key="p.id" class="card overflow-hidden p-0">
            <img v-if="p.image_url" :src="p.image_url" class="w-full h-40 object-cover" />
            <div class="p-4">
              <div class="flex items-center gap-2">
                <span v-if="p.pinned" class="tag" style="background:#fef3c7;color:#92400e">置顶</span>
                <h3 class="flex-1">{{ p.title }} <span class="tag ml-1">{{ p.status }}</span>
                  <span v-if="p.scope && p.scope!=='public'" class="tag ml-1">{{ p.scope_label }}</span></h3>
                <button v-if="isMe" class="text-xs" :class="p.pinned?'text-accent2':'text-accent'"
                  @click="togglePin(p)">{{ p.pinned ? '取消置顶' : '置顶' }}</button>
              </div>
              <p class="text-sm text-gray-500 mt-1 whitespace-pre-line">{{ p.body_zh }}</p>
            </div>
          </div>
          <p v-if="!projects.length" class="text-gray-400 text-sm">暂无项目。</p>
        </div>
      </div>

      <!-- 我的贡献 -->
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

      <!-- 个人简历 -->
      <div v-else-if="tab==='resume'">
        <div v-if="isMe" class="mb-3"><button class="btn-ghost" @click="openResumeEdit">编辑简历</button></div>
        <div v-for="b in resume.blocks" :key="b.id" class="mb-1.5">
          <component :is="b.type==='h'?'h2':b.type==='h2'?'h3':'p'"
            :class="b.type==='li'?'pl-4 list-item text-sm':b.type==='h'?'text-lg font-serif':b.type==='h2'?'font-medium':'text-sm text-gray-600'">
            {{ b.text_zh }}</component>
        </div>
        <p v-if="!resume.blocks.length" class="text-gray-400 text-sm">{{ isMe ? '还没有简历，点「编辑简历」开始填写。' : '暂无简历。' }}</p>
      </div>

      <!-- 项目工作台 -->
      <div v-else-if="tab==='ws'">
        <div v-if="isMe" class="mb-3"><button class="btn-primary" @click="openWsCreate">＋新建工作台</button></div>
        <div v-for="w in workspaces" :key="w.id" class="card mb-2 flex items-center justify-between">
          <span class="cursor-pointer flex-1" @click="openWs(w.id)">{{ w.title }}
            <span v-if="w.is_owner" class="tag ml-1">owner</span></span>
          <div class="flex items-center gap-3">
            <a v-if="w.overleaf_url" :href="w.overleaf_url" target="_blank" class="text-accent text-xs" @click.stop>Overleaf ↗</a>
            <button v-if="w.is_owner" class="text-accent2 text-xs" @click.stop="delWs(w.id)">删除</button>
          </div>
        </div>
        <p v-if="!workspaces.length" class="text-gray-400 text-sm">暂无项目工作台（私密协作，仅选定成员可见）。</p>
      </div>
    </div>

    <!-- ============ 编辑资料弹窗 ============ -->
    <div v-if="showEdit" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="closeEdit">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-lg">编辑资料</h3>
          <span v-if="dirty" class="text-[11px] text-amber-600">● 有未保存修改</span>
        </div>
        <div class="flex items-center gap-3 mb-3">
          <div class="w-16 h-16 rounded-full bg-paper overflow-hidden flex items-center justify-center">
            <img v-if="avatarPreview || editForm.avatar" :src="avatarPreview || editForm.avatar" class="w-full h-full object-cover" />
            <Icon v-else name="users" class="ico text-gray-300" style="width:24px;height:24px" />
          </div>
          <label class="btn-ghost text-xs cursor-pointer">更换头像
            <input type="file" accept="image/*" class="hidden" @change="pickAvatar" />
          </label>
        </div>
        <label class="label-cap">姓名</label>
        <input v-model="editForm.display_name" class="input mb-2" placeholder="显示名" />
        <label class="label-cap">研究方向</label>
        <input v-model="editForm.research_direction" class="input mb-2" placeholder="如：产业组织 / 发展经济学" />
        <label class="label-cap">关键词（逗号分隔）</label>
        <input v-model="editForm.keywords" class="input mb-4" placeholder="如：反垄断, 平台经济, 因果推断" />
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="closeEdit">取消</button>
          <button class="btn-primary" :disabled="saving" @click="saveEdit">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>

    <!-- ============ 编辑简历弹窗 ============ -->
    <div v-if="showResumeEdit" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="closeResumeEdit">
      <div class="bg-white rounded-lg max-w-2xl w-full p-6 m-4">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-lg">编辑简历</h3>
          <span v-if="resumeDirty" class="text-[11px] text-amber-600">● 有未保存修改</span>
        </div>
        <p class="text-xs text-gray-500 mb-2">一个文本框搞定整份简历：<b># 大标题</b>，<b>## 小标题</b>，<b>- 分点</b>，其余为正文。每行一条，保存即生效。</p>
        <textarea v-model="resumeText" rows="14" class="input font-mono text-sm"
          placeholder="# 教育经历&#10;## 北京大学 · 经济学博士&#10;- 2020–2025&#10;主要研究产业组织与平台经济。"></textarea>
        <div class="flex justify-end gap-2 mt-3">
          <button class="btn-ghost" @click="closeResumeEdit">取消</button>
          <button class="btn-primary" @click="saveResume">保存</button>
        </div>
      </div>
    </div>

    <!-- ============ 创建项目弹窗 ============ -->
    <div v-if="showProjCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showProjCreate=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-3">创建项目 <span class="text-xs text-gray-400">标题·图片·文字均必填</span></h3>
        <input v-model="projForm.title" class="input mb-2" placeholder="项目标题 *" />
        <label class="btn-ghost text-xs cursor-pointer inline-block mb-2">选择封面图片 *
          <input type="file" accept="image/*" class="hidden" @change="pickProjImage" />
        </label>
        <img v-if="projImgPreview" :src="projImgPreview" class="w-full h-40 object-cover rounded mb-2" />
        <textarea v-model="projForm.body_zh" rows="4" class="input mb-2" placeholder="项目介绍文字 *"></textarea>
        <div class="mb-2"><ScopeSelector v-model="projScope" /></div>
        <label class="flex items-center gap-2 text-sm mb-3">
          <input type="checkbox" v-model="projForm.pinned" /> 创建后置顶展示
        </label>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showProjCreate=false">取消</button>
          <button class="btn-primary" @click="createProject">创建</button>
        </div>
      </div>
    </div>

    <!-- ============ 新建工作台弹窗（含邀请成员检索）============ -->
    <div v-if="showWsCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showWsCreate=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <h3 class="text-lg mb-3">新建项目工作台</h3>
        <input v-model="wsForm.title" class="input mb-2" placeholder="标题 *" />
        <input v-model="wsForm.overleaf_url" class="input mb-3" placeholder="Overleaf 链接（可选）" />
        <label class="label-cap">邀请成员（按姓名或 ID 检索平台成员）</label>
        <div class="flex gap-2 mb-2">
          <input v-model="memberQ" class="input" placeholder="输入姓名或 ID" @keyup.enter="searchMembers" />
          <button class="btn-ghost text-xs" @click="searchMembers">检索</button>
        </div>
        <div v-if="memberResults.length" class="border border-line rounded mb-2 max-h-40 overflow-y-auto">
          <button v-for="u in memberResults" :key="u.id" class="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-paper"
            @click="inviteMember(u)">
            <span>{{ u.display_name }} <span class="text-gray-400 text-xs">ID {{ u.id }} · {{ u.username }}</span></span>
            <span class="text-accent text-xs">＋邀请</span>
          </button>
        </div>
        <div v-if="wsInvited.length" class="flex flex-wrap gap-1.5 mb-3">
          <span v-for="m in wsInvited" :key="m.id" class="tag flex items-center gap-1">
            {{ m.name }} <button class="text-accent2" @click="removeInvited(m.id)">×</button>
          </span>
        </div>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showWsCreate=false">取消</button>
          <button class="btn-primary" @click="createWs">创建</button>
        </div>
      </div>
    </div>

    <!-- ============ 工作台详情（时间轴相册 + 分类）============ -->
    <div v-if="wsModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="wsModal=null">
      <div class="bg-white rounded-lg max-w-3xl w-full p-6 m-4 max-h-[88vh] overflow-y-auto">
        <div class="flex items-center justify-between">
          <div>
            <h3 class="text-lg">{{ wsModal.title }}</h3>
            <div class="text-xs text-gray-400 mt-0.5">成员：{{ (wsModal.member_list||[]).map((m)=>m.name).join('、') }}</div>
          </div>
          <button @click="wsModal=null" class="text-gray-400"><Icon name="close" class="ico" style="width:18px;height:18px" /></button>
        </div>
        <a v-if="wsModal.overleaf_url" :href="wsModal.overleaf_url" target="_blank" class="text-accent text-xs">Overleaf ↗</a>

        <!-- 新增条目 -->
        <div class="card mt-4">
          <div class="flex gap-2 mb-2">
            <select v-model="entryForm.category" class="input w-28">
              <option v-for="(zh,k) in CATS" :key="k" :value="k">{{ zh }}</option>
            </select>
            <input v-model="entryForm.title" class="input" placeholder="标题（可选）" />
          </div>
          <textarea v-model="entryForm.body" rows="2" class="input mb-2" placeholder="记录一条进展 / 结果 / 讨论…"></textarea>
          <div class="flex items-center justify-between">
            <input type="file" class="text-xs" @change="(e)=>entryFile=e.target.files[0]" />
            <button class="btn-primary text-sm" @click="addEntry">＋添加到时间轴</button>
          </div>
        </div>

        <!-- 分类过滤 -->
        <div class="flex flex-wrap gap-1 mt-4 text-xs">
          <button :class="['px-2.5 py-1 rounded-full', entryCat==='all'?'bg-accent text-white':'bg-paper text-gray-600']"
            @click="entryCat='all'">全部（{{ (wsModal.entries||[]).length }}）</button>
          <button v-for="(zh,k) in CATS" :key="k" v-show="entryCatCounts[k]"
            :class="['px-2.5 py-1 rounded-full', entryCat===k?'bg-accent text-white':'bg-paper text-gray-600']"
            @click="entryCat=k">{{ zh }}（{{ entryCatCounts[k] }}）</button>
        </div>

        <!-- 时间轴相册 -->
        <div class="mt-4 relative pl-5">
          <div class="absolute left-1.5 top-1 bottom-1 w-px bg-line"></div>
          <div v-for="e in filteredEntries" :key="e.id" class="relative mb-5">
            <span class="absolute -left-[14px] top-1.5 w-2.5 h-2.5 rounded-full bg-accent border-2 border-white"></span>
            <div class="flex items-center gap-2 text-xs text-gray-400">
              <span class="tag">{{ CATS[e.category] || '其他' }}</span>
              <span>{{ e.author_name }}</span>
              <span>{{ (e.created_at||'').slice(0,16).replace('T',' ') }}</span>
              <button class="ml-auto text-accent2" @click="delEntry(e.id)">删除</button>
            </div>
            <div class="font-medium text-sm mt-1" v-if="e.title">{{ e.title }}</div>
            <p v-if="e.body" class="text-sm text-gray-600 whitespace-pre-line mt-0.5">{{ e.body }}</p>
            <img v-if="e.is_image && e.file_url" :src="e.file_url" class="mt-2 rounded max-h-56 border border-line" />
            <a v-else-if="e.has_file" :href="e.file_url" target="_blank"
              class="text-accent text-xs mt-1 inline-flex items-center gap-1 hover:underline">
              <Icon name="clip" class="ico" style="width:12px;height:12px" /> {{ e.file_name }}</a>
          </div>
          <p v-if="!filteredEntries.length" class="text-gray-400 text-sm">这个分类下还没有内容。</p>
        </div>
      </div>
    </div>
  </div>
</template>
