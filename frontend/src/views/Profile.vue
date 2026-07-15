<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuth } from '../stores/auth'
import api from '../api'
import Icon from '../components/Icon.vue'
import ScopeSelector from '../components/ScopeSelector.vue'
import PostCard from '../components/PostCard.vue'
import PostComposer from '../components/PostComposer.vue'

const route = useRoute(); const router = useRouter(); const { t } = useI18n(); const auth = useAuth()
const uid = ref<number>(0)
const profile = ref<any>(null); const tab = ref('projects')
const projects = ref<any[]>([]); const contrib = ref<any>({ total: 0, breakdown: [], events: [], hidden_count: 0 })
const resume = ref<any>({ blocks: [] }); const workspaces = ref<any[]>([])
const isMe = ref(false)
// 我的讨论
const myPosts = ref<any[]>([]); const postFilter = ref<any>({ scope: '', status: '' })
const discussComposerOpen = ref(false); const discussEditing = ref<any>(null)

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
  // 贡献度：本人看完整明细，他人看公开汇总 + 有权限的明细
  contrib.value = (await api.get(`/users/${uid.value}/contributions`)).data
  await loadMyPosts()
  if (isMe.value) {
    workspaces.value = (await api.get('/workspaces')).data
  }
}

async function loadMyPosts() {
  const params: any = { author_id: uid.value }
  if (postFilter.value.scope) params.scope = postFilter.value.scope
  if (postFilter.value.status) params.status = postFilter.value.status
  myPosts.value = (await api.get('/posts', { params })).data
}
function setPostFilter(key: string, val: string) {
  postFilter.value[key] = postFilter.value[key] === val ? '' : val
  loadMyPosts()
}
function openDiscussCompose() { discussEditing.value = null; discussComposerOpen.value = true }
function onDiscussEdit(post: any) { discussEditing.value = post; discussComposerOpen.value = true }
function onDiscussDeleted(id: number) { myPosts.value = myPosts.value.filter(p => p.id !== id) }

// ==================== 图片压缩（上传前，显著提速）====================
// 大照片在浏览器端先等比缩小 + 转 JPEG，再上传，减少体积、提升丝滑度。
async function compressImage(file: File, maxDim = 1600, quality = 0.82): Promise<File> {
  if (!file.type.startsWith('image/') || file.type === 'image/gif') return file
  try {
    const url = URL.createObjectURL(file)
    const img = new Image()
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = url })
    let w = img.naturalWidth, h = img.naturalHeight
    const scale = Math.min(1, maxDim / Math.max(w, h))
    w = Math.round(w * scale); h = Math.round(h * scale)
    const canvas = document.createElement('canvas')
    canvas.width = w; canvas.height = h
    canvas.getContext('2d')!.drawImage(img, 0, 0, w, h)
    URL.revokeObjectURL(url)
    const blob: Blob | null = await new Promise((res) => canvas.toBlob(b => res(b), 'image/jpeg', quality))
    if (!blob || blob.size >= file.size) return file   // 没变小就用原图
    return new File([blob], file.name.replace(/\.\w+$/, '') + '.jpg', { type: 'image/jpeg' })
  } catch { return file }
}

// ==================== 编辑资料 ====================
const showEdit = ref(false)
const editForm = ref<any>({ display_name: '', research_direction: '', keywords: '', email: '', avatar: '' })
const editSnapshot = ref('')
const avatarFile = ref<File | null>(null); const avatarPreview = ref('')
const saving = ref(false)
const dirty = computed(() => JSON.stringify(editForm.value) !== editSnapshot.value || !!avatarFile.value)

function openEdit() {
  editForm.value = {
    display_name: profile.value.display_name || '',
    research_direction: profile.value.research_direction || '',
    keywords: profile.value.keywords || '',
    email: profile.value.email || '',
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
      const fd = new FormData(); fd.append('file', await compressImage(avatarFile.value, 512, 0.85))
      const r = await api.post('/me/avatar', fd)
      editForm.value.avatar = r.data.avatar
    }
    await api.patch('/me', {
      display_name: editForm.value.display_name,
      research_direction: editForm.value.research_direction,
      keywords: editForm.value.keywords,
      email: editForm.value.email
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

// ==================== 简历（整块编辑 + AI 一键排版）====================
// 用一个文本框编辑整份简历：# 大标题 / ## 小标题 / - 分点 / 其余正文
const showResumeEdit = ref(false)
const resumeText = ref(''); const resumeSnapshot = ref('')
const aiFormatting = ref(false); const resumeSaving = ref(false)
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
async function aiFormatResume() {
  if (!resumeText.value.trim()) { alert('请先填写简历内容，再让 AI 排版'); return }
  if (!confirm('AI 会把当前文本重新归类排版（# 大标题 / ## 小标题 / - 分点），只整理不虚构。是否继续？')) return
  aiFormatting.value = true
  try {
    const r = await api.post('/me/resume/ai-format', { text: resumeText.value })
    resumeText.value = r.data.text
  } catch (e: any) { alert(e.response?.data?.detail || 'AI 排版失败') }
  finally { aiFormatting.value = false }
}
async function saveResume() {
  resumeSaving.value = true
  try {
    await api.put('/me/resume/blocks', { blocks: textToBlocks(resumeText.value) })
    resume.value = (await api.get(`/users/${uid.value}/resume`)).data
    resumeSnapshot.value = resumeText.value
    showResumeEdit.value = false
  } catch (e: any) { alert(e.response?.data?.detail || '保存失败') }
  finally { resumeSaving.value = false }
}

// ==================== 在做项目：创建 + 置顶 + 详情/编辑/删除/评论 ====================
// 预设标签（可多选，也可自定义）
const PROJECT_LABELS = ['欢迎讨论', '欢迎合作', '招募成员', '寻找数据', '寻求建议', '找合作者', '已完成']
const projLabelFilter = ref('')   // 项目列表按标签筛选（''=全部）
const showProjCreate = ref(false); const projSaving = ref(false)
const projForm = ref<any>({ title: '', body_zh: '', pinned: false, labels: [] as string[] })
const projLabelInput = ref('')     // 自定义标签输入（创建）
const editLabelInput = ref('')     // 自定义标签输入（编辑）
function toggleLabel(list: string[], lb: string) {
  const i = list.indexOf(lb)
  if (i >= 0) list.splice(i, 1); else list.push(lb)
}
function addCustomLabel(list: string[], val: string, clear: () => void) {
  const s = (val || '').trim().slice(0, 20)
  if (s && !list.includes(s)) list.push(s)
  clear()
}
// 当前用户项目里出现过的标签（用于筛选栏）
const projectLabelsInUse = computed(() => {
  const s = new Set<string>()
  for (const p of projects.value) for (const l of (p.labels || [])) s.add(l)
  return Array.from(s)
})
const filteredProjects = computed(() =>
  projLabelFilter.value
    ? projects.value.filter(p => (p.labels || []).includes(projLabelFilter.value))
    : projects.value)
const projScope = ref<{ scope: string; scope_ref_ids: number[] }>({ scope: 'public', scope_ref_ids: [] })
const projImage = ref<File | null>(null); const projImgPreview = ref('')
function pickProjImage(e: any) {
  const f = e.target.files?.[0]; if (!f) return
  projImage.value = f; projImgPreview.value = URL.createObjectURL(f)
}
function openProjCreate() {
  projForm.value = { title: '', body_zh: '', pinned: false, labels: [] }
  projLabelInput.value = ''
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
  projSaving.value = true
  try {
    const fd = new FormData()
    fd.append('title', projForm.value.title.trim())
    fd.append('body_zh', projForm.value.body_zh.trim())
    fd.append('pinned', String(projForm.value.pinned))
    fd.append('scope', projScope.value.scope)
    if (projScope.value.scope_ref_ids.length) fd.append('scope_ref_ids', projScope.value.scope_ref_ids.join(','))
    if (projForm.value.labels.length) fd.append('labels', projForm.value.labels.join(','))
    fd.append('image', await compressImage(projImage.value))
    await api.post('/projects', fd)
    showProjCreate.value = false
    projects.value = (await api.get('/projects', { params: { author_id: uid.value } })).data
  } catch (e: any) { alert(e.response?.data?.detail || '创建失败') }
  finally { projSaving.value = false }
}
async function togglePin(p: any) {
  const next = !p.pinned
  try {
    await api.post(`/projects/${p.id}/pin`, null, { params: { pinned: next } })
    projects.value = (await api.get('/projects', { params: { author_id: uid.value } })).data
    if (projDetail.value && projDetail.value.id === p.id) projDetail.value.pinned = next
  } catch (e: any) { alert(e.response?.data?.detail || '操作失败') }
}

// —— 项目详情 / 编辑 / 评论 ——
const projDetail = ref<any>(null)
const projComments = ref<any[]>([])
const projEdit = ref(false); const projEditForm = ref<any>({ title: '', body_zh: '' })
const projEditScope = ref<{ scope: string; scope_ref_ids: number[] }>({ scope: 'public', scope_ref_ids: [] })
const commentText = ref(''); const replyTo = ref<any>(null); const commentPosting = ref(false)
async function openProject(id: number) {
  projEdit.value = false; commentText.value = ''; replyTo.value = null
  try {
    projDetail.value = (await api.get(`/projects/${id}`)).data
    projComments.value = (await api.get(`/projects/${id}/comments`)).data
  } catch (e: any) { alert(e.response?.data?.detail || '打开失败') }
}
function startProjEdit() {
  projEditForm.value = {
    title: projDetail.value.title, body_zh: projDetail.value.body_zh || '',
    labels: [...(projDetail.value.labels || [])]
  }
  projEditScope.value = {
    scope: projDetail.value.scope || 'public',
    scope_ref_ids: [...(projDetail.value.scope_ref_ids || [])]
  }
  editLabelInput.value = ''
  projEdit.value = true
}
async function saveProjEdit() {
  if (!projEditForm.value.title.trim()) { alert('标题不能为空'); return }
  const sc = projEditScope.value
  if ((sc.scope === 'group' || sc.scope === 'dataset') && !sc.scope_ref_ids.length) {
    alert('请勾选至少一个课题组/数据集'); return
  }
  try {
    await api.patch(`/projects/${projDetail.value.id}`, {
      title: projEditForm.value.title.trim(), body_zh: projEditForm.value.body_zh,
      labels: projEditForm.value.labels,
      scope: sc.scope, scope_ref_ids: sc.scope_ref_ids
    })
    // 重新拉详情，拿到最新 scope_label / scope_ref_ids
    projDetail.value = (await api.get(`/projects/${projDetail.value.id}`)).data
    projEdit.value = false
    projects.value = (await api.get('/projects', { params: { author_id: uid.value } })).data
  } catch (e: any) { alert(e.response?.data?.detail || '保存失败') }
}
async function deleteProject() {
  if (!confirm('确定删除这个项目？（评论也会一并删除）')) return
  try {
    await api.delete(`/projects/${projDetail.value.id}`)
    projDetail.value = null
    projects.value = (await api.get('/projects', { params: { author_id: uid.value } })).data
  } catch (e: any) { alert(e.response?.data?.detail || '删除失败') }
}
const topComments = computed(() => projComments.value.filter(c => !c.parent_id))
function repliesOf(cid: number) { return projComments.value.filter(c => c.parent_id === cid) }
async function postComment() {
  if (!commentText.value.trim()) return
  commentPosting.value = true
  try {
    await api.post(`/projects/${projDetail.value.id}/comments`, {
      content: commentText.value.trim(), parent_id: replyTo.value?.id || null
    })
    commentText.value = ''; replyTo.value = null
    projComments.value = (await api.get(`/projects/${projDetail.value.id}/comments`)).data
  } catch (e: any) { alert(e.response?.data?.detail || '评论失败') }
  finally { commentPosting.value = false }
}
async function delComment(c: any) {
  if (!confirm('删除这条评论？')) return
  await api.delete(`/projects/${projDetail.value.id}/comments/${c.id}`)
  projComments.value = (await api.get(`/projects/${projDetail.value.id}/comments`)).data
}

// ==================== 我的贡献：跳转数据集 ====================
function gotoContrib(e: any) {
  if (e.dataset_slug) router.push(`/datasets/${e.dataset_slug}`)
}

// ==================== 项目工作台 ====================
const showWsCreate = ref(false); const wsSaving = ref(false)
const wsForm = ref<any>({ title: '', overleaf_url: '' })
const wsInvited = ref<any[]>([])          // 已选邀请成员 {id,name}
const wsModal = ref<any>(null)
const entryCat = ref('all')
const entryForm = ref<any>({ category: 'progress', title: '', body: '' })
const entryFile = ref<File | null>(null); const entrySaving = ref(false)

const CATS: Record<string, string> = {
  progress: '进展', data: '数据', figure: '图表', literature: '文献',
  result: '结果', discussion: '讨论', other: '其他'
}

// 新建时的成员检索（按姓名/ID）
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
  wsSaving.value = true
  try {
    await api.post('/workspaces', {
      title: wsForm.value.title.trim(),
      overleaf_url: wsForm.value.overleaf_url || null,
      member_ids: wsInvited.value.map(x => x.id)
    })
    showWsCreate.value = false; reloadWs()
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
  finally { wsSaving.value = false }
}
async function openWs(id: number) {
  wsModal.value = (await api.get(`/workspaces/${id}`)).data; entryCat.value = 'all'
  wsMemberQ.value = ''; wsMemberResults.value = []
}
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
  entrySaving.value = true
  try {
    const fd = new FormData()
    fd.append('category', entryForm.value.category)
    fd.append('title', entryForm.value.title)
    fd.append('body', entryForm.value.body)
    if (entryFile.value) fd.append('file', await compressImage(entryFile.value))
    await api.post(`/workspaces/${wsModal.value.id}/entries`, fd)
    entryForm.value = { category: entryForm.value.category, title: '', body: '' }
    entryFile.value = null
    openWs(wsModal.value.id)
  } catch (e: any) { alert(e.response?.data?.detail || '添加失败') }
  finally { entrySaving.value = false }
}
async function delEntry(eid: number) {
  if (!confirm('删除这条记录？')) return
  await api.delete(`/workspaces/${wsModal.value.id}/entries/${eid}`); openWs(wsModal.value.id)
}

// —— 工作台成员管理（创建者拉人/踢人）——
const wsMemberQ = ref(''); const wsMemberResults = ref<any[]>([])
async function searchWsMembers() {
  const q = wsMemberQ.value.trim()
  const existing = new Set((wsModal.value?.member_list || []).map((m: any) => m.id))
  wsMemberResults.value = (await api.get('/users/search', { params: { q } })).data
    .filter((u: any) => !existing.has(u.id))
}
async function addWsMember(u: any) {
  try {
    await api.post(`/workspaces/${wsModal.value.id}/members/${u.id}`)
    wsMemberResults.value = wsMemberResults.value.filter(x => x.id !== u.id)
    openWs(wsModal.value.id)
  } catch (e: any) { alert(e.response?.data?.detail || '添加失败') }
}
async function removeWsMember(m: any) {
  if (!confirm(`将「${m.name}」移出工作台？`)) return
  try {
    await api.delete(`/workspaces/${wsModal.value.id}/members/${m.id}`)
    openWs(wsModal.value.id)
  } catch (e: any) { alert(e.response?.data?.detail || '移除失败') }
}
</script>
<template>
  <div v-if="profile">
    <!-- 顶部资料卡 -->
    <div class="rounded-lg p-6 text-white" style="background: linear-gradient(135deg,#2d4a7c,#3d5a8c)">
      <div class="flex items-start gap-4">
        <div class="w-16 h-16 rounded-full bg-white/20 flex items-center justify-center overflow-hidden shrink-0">
          <img v-if="profile.avatar" :src="profile.avatar" class="w-full h-full object-cover" />
          <Icon v-else name="users" class="ico" style="width:26px;height:26px" />
        </div>
        <div class="min-w-0 flex-1">
          <h1 class="text-2xl font-serif">{{ profile.display_name }}
            <span class="text-white/50 text-sm font-sans">ID {{ profile.id }}</span></h1>
          <p v-if="profile.research_direction" class="text-white/85 text-sm mt-0.5">
            研究方向：{{ profile.research_direction }}</p>
          <p v-if="profile.email" class="text-white/85 text-sm mt-0.5 flex items-center gap-1">
            <Icon name="mail" class="ico" style="width:13px;height:13px" />
            <a :href="`mailto:${profile.email}`" class="hover:underline">{{ profile.email }}</a></p>
          <div v-if="keywordList.length" class="flex flex-wrap gap-1 mt-1.5">
            <span v-for="k in keywordList" :key="k" class="text-[11px] bg-white/15 rounded px-2 py-0.5">{{ k }}</span>
          </div>
        </div>
        <!-- 右侧：编辑资料按钮在上，贡献度在下，纵向排列，互不重叠 -->
        <div class="flex flex-col items-end gap-2 shrink-0">
          <button v-if="isMe" class="text-xs bg-white/15 hover:bg-white/25 rounded px-3 py-1.5"
            @click="openEdit">编辑资料</button>
          <div class="text-right">
            <div class="text-3xl font-serif leading-none">{{ profile.contribution }}</div>
            <div class="label-cap text-white/70 mt-1">{{ t('profile.contribution') }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="flex gap-1 border-b border-line mt-5 text-sm">
      <button v-for="[k,l] in [['projects','在做的项目'],['discuss','我的讨论'],['contrib','我的贡献'],['resume','个人简历'],['ws','项目工作台']]"
        :key="k" @click="tab=k as string" :class="['px-3 py-2', tab===k?'border-b-2 border-accent text-accent':'text-gray-500']">
        {{ l }}
      </button>
    </div>

    <div class="py-5">
      <!-- 在做的项目 -->
      <div v-if="tab==='projects'">
        <!-- 创建按钮 + 按标签分类检索 -->
        <div class="flex items-center gap-2 flex-wrap mb-3">
          <button v-if="isMe" class="btn-primary" @click="openProjCreate">＋创建项目</button>
          <div class="flex items-center gap-1 flex-wrap text-xs">
            <button :class="['px-2.5 py-1 rounded-full border', !projLabelFilter ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
              @click="projLabelFilter=''">全部</button>
            <button v-for="lb in projectLabelsInUse" :key="lb"
              :class="['px-2.5 py-1 rounded-full border', projLabelFilter===lb ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
              @click="projLabelFilter = projLabelFilter===lb ? '' : lb">{{ lb }}</button>
          </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div v-for="p in filteredProjects" :key="p.id" class="card overflow-hidden p-0 cursor-pointer hover:shadow-md transition"
            @click="openProject(p.id)">
            <img v-if="p.image_url" :src="p.image_url" class="w-full h-40 object-cover" />
            <div class="p-4">
              <div class="flex items-center gap-2">
                <span v-if="p.pinned" class="tag" style="background:#fef3c7;color:#92400e">置顶</span>
                <h3 class="flex-1">{{ p.title }} <span class="tag ml-1">{{ p.status }}</span>
                  <span v-if="p.scope && p.scope!=='public'" class="tag ml-1">{{ p.scope_label }}</span></h3>
                <button v-if="isMe" class="text-xs" :class="p.pinned?'text-accent2':'text-accent'"
                  @click.stop="togglePin(p)">{{ p.pinned ? '取消置顶' : '置顶' }}</button>
              </div>
              <div v-if="p.labels && p.labels.length" class="flex flex-wrap gap-1 mt-1.5">
                <span v-for="lb in p.labels" :key="lb" class="tag" style="background:#eef2f8;color:#2d4a7c">{{ lb }}</span>
              </div>
              <p class="text-sm text-gray-500 mt-1 whitespace-pre-line line-clamp-3">{{ p.body_zh }}</p>
              <div class="text-xs text-accent mt-2">点击查看详情与评论 →</div>
            </div>
          </div>
          <p v-if="!filteredProjects.length" class="text-gray-400 text-sm">{{ projLabelFilter ? '该标签下暂无项目。' : '暂无项目。' }}</p>
        </div>
      </div>

      <!-- 我的贡献（本人看完整明细；他人看公开汇总 + 有权限的明细）-->
      <div v-else-if="tab==='contrib'">
        <div class="card">
          <div class="flex items-baseline gap-3 flex-wrap">
            <div><span class="label-cap">总贡献度</span>
              <span class="text-2xl font-serif ml-1">{{ contrib.total }}</span></div>
            <div class="flex flex-wrap gap-2">
              <span v-for="b in contrib.breakdown" :key="b.label" class="tag" style="background:#eef2f8;color:#2d4a7c">
                {{ b.label }} {{ b.count }} 次</span>
            </div>
          </div>
          <table class="w-full text-sm mt-3">
            <tr v-for="(e,i) in contrib.events" :key="i" class="border-t border-line"
              :class="e.dataset_slug ? 'hover:bg-paper cursor-pointer' : ''" @click="gotoContrib(e)">
              <td class="py-1.5"><span class="tag">{{ e.category || e.type }}</span></td>
              <td>
                <span v-if="e.dataset_name" class="text-accent inline-flex items-center gap-1">
                  <Icon name="chart" class="ico" style="width:13px;height:13px" />{{ e.dataset_name }}
                  <span class="text-gray-400 text-xs">· {{ e.ref_type }} #{{ e.ref_id }}</span>
                </span>
                <span v-else class="text-gray-500">{{ e.ref_type }} #{{ e.ref_id }}</span>
              </td>
              <td class="text-right whitespace-nowrap">
                <span v-if="e.dataset_slug" class="text-accent text-xs mr-2">跳转 →</span>
                <span class="font-mono">+{{ e.weight }}</span>
              </td>
            </tr>
          </table>
          <p v-if="contrib.hidden_count" class="text-gray-400 text-sm mt-2">另有 {{ contrib.hidden_count }} 项非公开贡献（来自你无权访问的数据集/内部内容）。</p>
          <p v-if="!contrib.events.length && !contrib.hidden_count" class="text-gray-400 text-sm mt-2">暂无贡献记录。</p>
        </div>
      </div>

      <!-- 我的讨论（与研究广场同一套帖子，改动即时同步）-->
      <div v-else-if="tab==='discuss'">
        <div class="flex items-center justify-between mb-3">
          <div class="flex flex-wrap gap-1 text-xs">
            <button v-for="s in [['','全部'],['public','公开'],['group','课题组可见'],['dataset','数据集可见']]" :key="s[0]"
              :class="['px-2.5 py-1 rounded-full border', postFilter.scope===s[0] ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
              @click="postFilter.scope!==s[0] ? (postFilter.scope=s[0], loadMyPosts()) : null">{{ s[1] }}</button>
            <button :class="['px-2.5 py-1 rounded-full border', postFilter.status==='resolved' ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
              @click="setPostFilter('status','resolved')">已解决</button>
          </div>
          <button v-if="isMe" class="btn-primary text-sm" @click="openDiscussCompose">＋发布讨论</button>
        </div>
        <PostCard v-for="p in myPosts" :key="p.id" :post="p" :current-user-id="auth.user?.id"
          @edit="onDiscussEdit" @deleted="onDiscussDeleted" @changed="loadMyPosts" />
        <p v-if="!myPosts.length" class="text-gray-400 text-sm">{{ isMe ? '你还没有发布讨论，点「发布讨论」开始。' : '该用户暂无公开讨论。' }}</p>
      </div>

      <!-- 个人简历 -->
      <div v-else-if="tab==='resume'">
        <div v-if="isMe" class="mb-3"><button class="btn-ghost" @click="openResumeEdit">编辑简历</button></div>
        <div v-for="b in resume.blocks" :key="b.id" class="mb-1.5">
          <h2 v-if="b.type==='h'" class="text-lg font-serif">{{ b.text_zh }}</h2>
          <h3 v-else-if="b.type==='h2'" class="font-medium">{{ b.text_zh }}</h3>
          <div v-else-if="b.type==='li'" class="flex gap-2 text-sm pl-4">
            <span class="mt-[7px] w-1 h-1 rounded-full bg-accent shrink-0"></span>
            <span class="text-gray-700">{{ b.text_zh }}</span>
          </div>
          <p v-else class="text-sm text-gray-600">{{ b.text_zh }}</p>
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
        <input v-model="editForm.keywords" class="input mb-2" placeholder="如：反垄断, 平台经济, 因果推断" />
        <label class="label-cap">公开联系邮箱（选填，将展示在主页卡片）</label>
        <input v-model="editForm.email" type="email" class="input mb-4" placeholder="如：name@school.edu.cn" />
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
        <p class="text-xs text-gray-500 mb-2">一个文本框搞定整份简历：<b># 大标题</b>，<b>## 小标题</b>，<b>- 分点</b>，其余为正文。每行一条，保存即生效。也可先随意粘贴，再用「AI 一键排版」自动归类。</p>
        <textarea v-model="resumeText" rows="14" class="input font-mono text-sm"
          placeholder="# 教育经历&#10;## 北京大学 · 经济学博士&#10;- 2020–2025&#10;主要研究产业组织与平台经济。"></textarea>
        <div class="flex justify-between items-center gap-2 mt-3">
          <button class="btn-ghost text-sm inline-flex items-center gap-1" :disabled="aiFormatting" @click="aiFormatResume">
            <Icon name="sparkle" class="ico" style="width:14px;height:14px" />
            {{ aiFormatting ? 'AI 排版中…' : 'AI 一键排版' }}</button>
          <div class="flex gap-2">
            <button class="btn-ghost" @click="closeResumeEdit">取消</button>
            <button class="btn-primary" :disabled="resumeSaving" @click="saveResume">{{ resumeSaving ? '保存中…' : '保存' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ 创建项目弹窗 ============ -->
    <div v-if="showProjCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showProjCreate=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <h3 class="text-lg mb-3">创建项目 <span class="text-xs text-gray-400">标题·图片·文字均必填</span></h3>
        <input v-model="projForm.title" class="input mb-2" placeholder="项目标题 *" />
        <label class="btn-ghost text-xs cursor-pointer inline-block mb-1">选择封面图片 *
          <input type="file" accept="image/*" class="hidden" @change="pickProjImage" />
        </label>
        <p class="text-[11px] text-gray-400 mb-2">建议使用横版图片（约 16:9），卡片按封面等比裁剪展示；过大图片会自动压缩后上传。</p>
        <img v-if="projImgPreview" :src="projImgPreview" class="w-full h-40 object-cover rounded mb-2" />
        <textarea v-model="projForm.body_zh" rows="4" class="input mb-2" placeholder="项目介绍文字 *"></textarea>

        <label class="label-cap">标签（可多选，会展示在项目上，也支持自定义）</label>
        <div class="flex flex-wrap gap-1 mb-1.5">
          <button v-for="lb in PROJECT_LABELS" :key="lb" type="button"
            :class="['text-xs px-2.5 py-1 rounded-full border', projForm.labels.includes(lb) ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
            @click="toggleLabel(projForm.labels, lb)">{{ lb }}</button>
        </div>
        <div class="flex flex-wrap gap-1 items-center mb-2">
          <span v-for="lb in projForm.labels.filter(x => !PROJECT_LABELS.includes(x))" :key="lb"
            class="tag flex items-center gap-1" style="background:#eef2f8;color:#2d4a7c">
            {{ lb }} <button type="button" class="text-accent2" @click="toggleLabel(projForm.labels, lb)">×</button></span>
          <input v-model="projLabelInput" class="input text-xs" style="width:130px" placeholder="自定义标签"
            @keyup.enter="addCustomLabel(projForm.labels, projLabelInput, () => projLabelInput='')" />
          <button type="button" class="btn-ghost text-xs" @click="addCustomLabel(projForm.labels, projLabelInput, () => projLabelInput='')">添加</button>
        </div>

        <div class="mb-2"><ScopeSelector v-model="projScope" /></div>
        <label class="flex items-center gap-2 text-sm mb-3">
          <input type="checkbox" v-model="projForm.pinned" /> 创建后置顶展示
        </label>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showProjCreate=false">取消</button>
          <button class="btn-primary" :disabled="projSaving" @click="createProject">{{ projSaving ? '创建中…' : '创建' }}</button>
        </div>
      </div>
    </div>

    <!-- ============ 项目详情 / 编辑 / 评论 ============ -->
    <div v-if="projDetail" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="projDetail=null">
      <div class="bg-white rounded-lg max-w-2xl w-full p-6 m-4 max-h-[88vh] overflow-y-auto">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="text-xl font-serif">{{ projDetail.title }}
              <span v-if="projDetail.pinned" class="tag ml-1" style="background:#fef3c7;color:#92400e">置顶</span></h3>
            <div class="text-xs text-gray-400 mt-1">
              {{ projDetail.author_name }} · {{ projDetail.status }}
              <span v-if="projDetail.scope && projDetail.scope!=='public'"> · {{ projDetail.scope_label }}</span>
            </div>
            <div v-if="!projEdit && projDetail.labels && projDetail.labels.length" class="flex flex-wrap gap-1 mt-1.5">
              <span v-for="lb in projDetail.labels" :key="lb" class="tag" style="background:#eef2f8;color:#2d4a7c">{{ lb }}</span>
            </div>
          </div>
          <button @click="projDetail=null" class="text-gray-400 shrink-0"><Icon name="close" class="ico" style="width:18px;height:18px" /></button>
        </div>

        <img v-if="projDetail.image_url" :src="projDetail.image_url"
          class="block mx-auto max-w-full max-h-[70vh] w-auto h-auto object-contain rounded mt-3 bg-paper" />

        <!-- 正文 / 编辑 -->
        <div v-if="!projEdit" class="mt-3">
          <p class="text-sm text-gray-700 whitespace-pre-line">{{ projDetail.body_zh }}</p>
        </div>
        <div v-else class="mt-3">
          <label class="label-cap">标题</label>
          <input v-model="projEditForm.title" class="input mb-2" placeholder="项目标题" />
          <label class="label-cap">正文</label>
          <textarea v-model="projEditForm.body_zh" rows="5" class="input mb-2" placeholder="项目介绍文字"></textarea>
          <label class="label-cap">标签</label>
          <div class="flex flex-wrap gap-1 mb-1.5">
            <button v-for="lb in PROJECT_LABELS" :key="lb" type="button"
              :class="['text-xs px-2.5 py-1 rounded-full border', projEditForm.labels.includes(lb) ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
              @click="toggleLabel(projEditForm.labels, lb)">{{ lb }}</button>
          </div>
          <div class="flex flex-wrap gap-1 items-center">
            <span v-for="lb in projEditForm.labels.filter(x => !PROJECT_LABELS.includes(x))" :key="lb"
              class="tag flex items-center gap-1" style="background:#eef2f8;color:#2d4a7c">
              {{ lb }} <button type="button" class="text-accent2" @click="toggleLabel(projEditForm.labels, lb)">×</button></span>
            <input v-model="editLabelInput" class="input text-xs" style="width:130px" placeholder="自定义标签"
              @keyup.enter="addCustomLabel(projEditForm.labels, editLabelInput, () => editLabelInput='')" />
            <button type="button" class="btn-ghost text-xs" @click="addCustomLabel(projEditForm.labels, editLabelInput, () => editLabelInput='')">添加</button>
          </div>
          <div class="mt-2"><ScopeSelector v-model="projEditScope" /></div>
          <div class="flex justify-end gap-2 mt-3">
            <button class="btn-ghost text-sm" @click="projEdit=false">取消</button>
            <button class="btn-primary text-sm" @click="saveProjEdit">保存修改</button>
          </div>
        </div>

        <!-- 作者操作 -->
        <div v-if="projDetail.can_edit && !projEdit" class="flex items-center gap-3 mt-3 text-sm">
          <button class="text-accent" @click="startProjEdit">编辑</button>
          <button class="text-accent" @click="togglePin(projDetail)">{{ projDetail.pinned ? '取消置顶' : '置顶' }}</button>
          <button v-if="projDetail.can_manage" class="text-accent2 ml-auto" @click="deleteProject">删除项目</button>
        </div>

        <!-- 评论 -->
        <div class="border-t border-line mt-5 pt-4">
          <div class="label-cap mb-2">交流讨论（{{ projComments.length }}）</div>
          <div v-if="projDetail.open_for_discussion || projDetail.can_edit" class="flex gap-2 mb-3">
            <input v-model="commentText" class="input"
              :placeholder="replyTo ? `回复 @${replyTo.user_name}…` : '写下你的评论 / 交流…'" @keyup.enter="postComment" />
            <button v-if="replyTo" class="btn-ghost text-xs" @click="replyTo=null">取消回复</button>
            <button class="btn-primary text-sm" :disabled="commentPosting" @click="postComment">发送</button>
          </div>
          <p v-else class="text-xs text-gray-400 mb-3">该项目未开放讨论。</p>

          <div v-for="c in topComments" :key="c.id" class="mb-3">
            <div class="flex items-start gap-2">
              <div class="flex-1">
                <div class="text-sm"><b>{{ c.user_name }}</b>
                  <span class="text-gray-400 text-xs ml-2">{{ c.created_at }}</span></div>
                <p class="text-sm text-gray-700 whitespace-pre-line">{{ c.content }}</p>
                <div class="text-xs mt-0.5 flex gap-3">
                  <button class="text-accent" @click="replyTo=c">回复</button>
                  <button v-if="c.can_delete" class="text-accent2" @click="delComment(c)">删除</button>
                </div>
              </div>
            </div>
            <!-- 回复 -->
            <div v-for="r in repliesOf(c.id)" :key="r.id" class="ml-6 mt-2 pl-3 border-l border-line">
              <div class="text-sm"><b>{{ r.user_name }}</b>
                <span class="text-gray-400 text-xs ml-2">{{ r.created_at }}</span></div>
              <p class="text-sm text-gray-700 whitespace-pre-line">{{ r.content }}</p>
              <div class="text-xs mt-0.5 flex gap-3">
                <button class="text-accent" @click="replyTo=c">回复</button>
                <button v-if="r.can_delete" class="text-accent2" @click="delComment(r)">删除</button>
              </div>
            </div>
          </div>
          <p v-if="!projComments.length" class="text-gray-400 text-sm">还没有评论，来说两句。</p>
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
          <button class="btn-primary" :disabled="wsSaving" @click="createWs">{{ wsSaving ? '创建中…' : '创建' }}</button>
        </div>
      </div>
    </div>

    <!-- ============ 工作台详情（时间轴相册 + 分类 + 成员管理）============ -->
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

        <!-- 成员管理（仅创建者）-->
        <div v-if="wsModal.is_owner" class="card mt-3">
          <div class="label-cap mb-2">成员管理（拉人 / 踢人）</div>
          <div class="flex flex-wrap gap-1.5 mb-2">
            <span v-for="m in wsModal.member_list" :key="m.id" class="tag flex items-center gap-1">
              {{ m.name }}<span v-if="m.is_owner" class="text-gray-400">· owner</span>
              <button v-if="!m.is_owner" class="text-accent2" @click="removeWsMember(m)">×</button>
            </span>
          </div>
          <div class="flex gap-2">
            <input v-model="wsMemberQ" class="input" placeholder="按姓名或 ID 检索成员" @keyup.enter="searchWsMembers" />
            <button class="btn-ghost text-xs" @click="searchWsMembers">检索</button>
          </div>
          <div v-if="wsMemberResults.length" class="border border-line rounded mt-2 max-h-40 overflow-y-auto">
            <button v-for="u in wsMemberResults" :key="u.id" class="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-paper"
              @click="addWsMember(u)">
              <span>{{ u.display_name }} <span class="text-gray-400 text-xs">ID {{ u.id }} · {{ u.username }}</span></span>
              <span class="text-accent text-xs">＋拉入</span>
            </button>
          </div>
        </div>

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
            <button class="btn-primary text-sm" :disabled="entrySaving" @click="addEntry">{{ entrySaving ? '添加中…' : '＋添加到时间轴' }}</button>
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
              <span>{{ e.created_at }}</span>
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

    <!-- ============ 发布/编辑讨论 ============ -->
    <PostComposer v-if="discussComposerOpen" :edit="discussEditing"
      @close="discussComposerOpen=false" @saved="loadMyPosts" />
  </div>
</template>
