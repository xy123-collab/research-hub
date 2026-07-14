<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api'
import CharterModal from '../components/CharterModal.vue'
import Icon from '../components/Icon.vue'

const route = useRoute(); const { t } = useI18n()
const slug = route.params.slug as string
const d = ref<any>(null); const tab = ref('overview')
const versions = ref<any[]>([]); const bugs = ref<any[]>([]); const vars = ref<any[]>([])
const codes = ref<any[]>([]); const flags = ref<any[]>([]); const dash = ref<any[]>([])
const lit = ref<any>({ topics: [], refs: [] }); const acceptedBugs = ref<any[]>([])
const bugForm = ref<any>({ officer_id: '', variable_id: null, current_value: '', suggested_value: '', description_zh: '' })
const bugFile = ref<File | null>(null)
const bugModal = ref<any>(null)
const codeModal = ref<any>(null)
const showPublish = ref(false); const showEdit = ref(false); const showCodeAdd = ref(false)
const pub = ref<any>({ version_id: '', changelog_zh: '', fixed: [] as number[] })
const pubData = ref<File | null>(null); const pubCode = ref<File | null>(null)
const edit = ref<any>({})
const codeAdd = ref<any>({ title_zh: '', lang: 'Python', desc_zh: '', source_code: '' })
const codeFile = ref<File | null>(null)
const aiPrompt = ref(''); const aiCode = ref(''); const aiResult = ref<any>(null); const aiSummary = ref('')
const litForm = ref<any>({ title: '', authors: '', venue: '', year: null, url: '', note_zh: '' })
const posts = ref<any[]>([]); const postForm = ref({ content_zh: '' })
const acts = ref<any[]>([]); const actFilter = ref('all')
// 权限相关：成员/授权/下载申请/设置
const mem = ref<any>({ members: [], requests: [], download_requests: [], grant_catalog: [] })
const showDlReq = ref(false)
const dlReq = ref<any>({ purpose: '', scope_version: '', planned_until: '', share_with_others: false, agree_charter: false })
const showGrant = ref(false); const grantTarget = ref<any>(null)
const grantForm = ref<any>({ perm: '', scope_type: 'permanent', valid_to: '', scope_version: '', project_note: '' })
const showSettings = ref(false)
const settingsForm = ref<any>({})
const showCand = ref(false); const candFile = ref<File | null>(null); const candNote = ref('')
const candidates = ref<any[]>([])

const tabs = computed(() => {
  const base: string[][] = [
    ['overview', 'ds.overview'], ['activity', 'ds.activity'], ['dashboard', 'ds.dashboard'],
    ['versions', 'ds.versions'], ['bugs', 'ds.bugs'], ['code', 'ds.code'],
    ['literature', 'ds.literature'], ['verify', 'ds.verify'], ['feed', 'ds.feed']
  ]
  if (d.value?.is_admin) base.push(['access', 'ds.access'])
  return base
})

// 权限派生：当前用户对「当前版本」的下载能力（用于按钮显隐，后端仍会二次校验）
const canDownloadCurrent = computed(() => {
  if (!d.value) return false
  if (d.value.is_admin) return true
  if (!d.value.is_member) return false
  const p = d.value.settings?.download_policy
  const perms = d.value.my_perms || []
  if (p === 'member' || p === 'public') return true
  if (p === 'approval') return perms.includes('download.current') || d.value.my_download_request?.status === 'approved'
  if (p === 'masked_only') return perms.includes('download.masked')
  return false
})
const canAnalyze = computed(() => {
  if (!d.value) return false
  if (d.value.is_admin || d.value.settings?.analysis_open) return true
  return (d.value.my_perms || []).includes('analysis.online')
})
const canUploadCandidate = computed(() =>
  d.value && (d.value.is_admin || (d.value.my_perms || []).includes('upload.candidate')))
const permLabel: Record<string, string> = {
  'download.current': '下载当前完整正式版本', 'download.masked': '下载脱敏数据',
  'version.history.view': '查看历史版本', 'download.history': '下载历史版本',
  'analysis.online': '在线分析功能', 'upload.candidate': '上传版本候选文件',
  'codebook.draft': '编辑 codebook 草稿', 'code.maintain': '上传和维护处理代码',
}
const policyLabel: Record<string, string> = {
  public: '公开数据（登录可下）', member: '成员可下载', approval: '审批后下载',
  masked_only: '仅脱敏数据可下载', forbidden: '禁止下载（仅在线分析）',
}

onMounted(async () => {
  d.value = (await api.get(`/datasets/${slug}`)).data
  vars.value = (await api.get(`/datasets/${slug}/variables`)).data
  if (d.value.is_admin) { try { await loadMembers() } catch {} }
  const q = route.query.tab as string
  loadTab(q && tabs.value.some(x => x[0] === q) ? q : 'overview')
  const bugId = route.query.bug as string
  if (bugId) openBug(Number(bugId))
})

async function reloadDetail() { d.value = (await api.get(`/datasets/${slug}`)).data }

async function loadTab(x: string) {
  tab.value = x
  if (x === 'versions') versions.value = (await api.get(`/datasets/${slug}/versions`)).data
  if (x === 'bugs') bugs.value = (await api.get(`/datasets/${slug}/bugs`)).data
  if (x === 'code') codes.value = (await api.get(`/datasets/${slug}/code`)).data
  if (x === 'verify') flags.value = (await api.get(`/datasets/${slug}/verify-flags`)).data
  if (x === 'literature') lit.value = (await api.get(`/datasets/${slug}/literature`)).data
  if (x === 'dashboard') dash.value = (await api.get(`/datasets/${slug}/dashboard`, { params: { var: 'gender' } })).data
  if (x === 'feed') posts.value = (await api.get('/posts', { params: { dataset_id: d.value.id } })).data
  if (x === 'activity') acts.value = (await api.get(`/datasets/${slug}/activity`, { params: { kind: actFilter.value } })).data
  if (x === 'access') await loadMembers()
}

// ---------- 成员与权限管理 ----------
async function loadMembers() {
  mem.value = (await api.get(`/datasets/${slug}/members`)).data
}
async function decideJoin(id: number, approve: boolean) {
  await api.post(`/join-requests/${id}/decide`, null, { params: { approve } })
  await loadMembers(); await reloadDetail()
}
async function decideDownload(id: number, approve: boolean) {
  let valid_to = ''
  if (approve) valid_to = prompt('可选：授权有效期（YYYY-MM-DD，留空为长期有效）', '') || ''
  await api.post(`/download-requests/${id}/decide`, null, { params: { approve, valid_to } })
  await loadMembers()
}
async function addAdmin(uid: number) {
  await api.post(`/datasets/${slug}/admins/${uid}`); await loadMembers(); await reloadDetail()
}
async function removeAdmin(uid: number) {
  try { await api.delete(`/datasets/${slug}/admins/${uid}`); await loadMembers(); await reloadDetail() }
  catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function removeDsMember(uid: number) {
  if (!confirm('确认移除该成员？其单独授权将一并撤销。')) return
  try { await api.delete(`/datasets/${slug}/members/${uid}`); await loadMembers() }
  catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
function openGrant(m: any) {
  grantTarget.value = m
  grantForm.value = { perm: mem.value.grant_catalog?.[0]?.perm || 'download.current', scope_type: 'permanent', valid_to: '', scope_version: '', project_note: '' }
  showGrant.value = true
}
async function doGrant() {
  try {
    await api.post(`/datasets/${slug}/members/${grantTarget.value.user_id}/grant`, grantForm.value)
    showGrant.value = false; await loadMembers()
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function revokePerm(uid: number, perm: string) {
  await api.post(`/datasets/${slug}/members/${uid}/revoke`, null, { params: { perm } }); await loadMembers()
}
// ---------- 下载申请（成员）----------
function openDlReq() {
  dlReq.value = { purpose: '', scope_version: d.value.current_version?.version_id || '', planned_until: '', share_with_others: false, agree_charter: false }
  showDlReq.value = true
}
async function submitDlReq() {
  try {
    await api.post(`/datasets/${slug}/download-requests`, dlReq.value)
    showDlReq.value = false; await reloadDetail(); alert('下载申请已提交，等待管理员审批')
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
// ---------- 数据集设置（管理员）----------
function openSettings() {
  settingsForm.value = { ...(d.value.settings || {}) }
  showSettings.value = true
}
async function saveSettings() {
  await api.patch(`/datasets/${slug}/settings`, settingsForm.value)
  showSettings.value = false; await reloadDetail()
}
async function toggleClose() {
  const closed = !d.value.settings?.is_closed
  if (!confirm(closed ? '确认关闭数据集？将不再接受新成员/勘误/发版。' : '确认重新开放数据集？')) return
  await api.post(`/datasets/${slug}/close`, null, { params: { closed } }); await reloadDetail()
}
// ---------- 版本候选文件 ----------
async function loadCandidates() { candidates.value = (await api.get(`/datasets/${slug}/candidates`)).data }
async function uploadCandidate() {
  if (!candFile.value) { alert('请选择文件'); return }
  const fd = new FormData(); fd.append('file', candFile.value); fd.append('note', candNote.value)
  try {
    await api.post(`/datasets/${slug}/candidates`, fd)
    showCand.value = false; candFile.value = null; candNote.value = ''; await loadCandidates()
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
// 两级管理员：转让总管理员
async function transferLead(uid: number) {
  if (!confirm('确认把「数据集总管理员」转让给该成员？你将降为普通管理员。')) return
  try { await api.post(`/datasets/${slug}/transfer-lead/${uid}`); await loadMembers(); await reloadDetail() }
  catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
function roleLabel(m: any) { return m.is_lead ? '总管理员' : (m.is_admin ? '管理员' : '成员') }
// 公约编辑
const showCharterEdit = ref(false); const charterForm = ref({ body_zh: '' })
function openCharterEdit() { charterForm.value = { body_zh: d.value.charter?.body_zh || '' }; showCharterEdit.value = true }
async function saveCharter() {
  await api.put(`/charters/${d.value.charter.id}`, charterForm.value)
  showCharterEdit.value = false; await reloadDetail()
}
// ---------- 成员弹窗（默认显示3个）----------
const showMembers = ref(false); const memberQ = ref('')
const filteredMembers = computed(() => {
  const q = memberQ.value.trim().toLowerCase()
  const list = d.value?.members || []
  if (!q) return list
  return list.filter((m: any) => (m.name || '').toLowerCase().includes(q) || String(m.user_id).includes(q))
})
// ---------- 版本数据分类 ----------
const kindLabel: Record<string, string> = { raw: '原始数据', masked: '脱敏数据', sample: '样例数据' }
const kindColor: Record<string, string> = { raw: 'border-accent text-accent', masked: 'border-emerald-600 text-emerald-700', sample: 'border-gray-400 text-gray-500' }
// ---------- 一键脱敏 ----------
const showDesens = ref(false); const desensForm = ref<any>({ from: null, new_version_id: '', changelog_zh: '' })
function openDesens(v: any) { desensForm.value = { from: v, new_version_id: '', changelog_zh: '' }; showDesens.value = true }
async function doDesensitize() {
  try {
    const fd = new FormData(); fd.append('new_version_id', desensForm.value.new_version_id)
    fd.append('changelog_zh', desensForm.value.changelog_zh)
    const r = await api.post(`/datasets/${slug}/versions/${desensForm.value.from.id}/desensitize`, fd)
    if (r.data.generated === 'script') { downloadText(r.data.script, 'desensitize.do'); alert(r.data.note) }
    else alert('已生成脱敏版本 ' + r.data.version_id)
    showDesens.value = false; loadTab('versions'); reloadDetail()
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
// ---------- 一键应用已采纳勘误 ----------
const showApply = ref(false); const applyForm = ref<any>({ base_version_id: null, new_version_id: '', changelog_zh: '' })
function openApply() {
  applyForm.value = { base_version_id: d.value.current_version?.id || null, new_version_id: '', changelog_zh: '' }
  showApply.value = true
}
async function doApply() {
  try {
    const fd = new FormData()
    fd.append('base_version_id', applyForm.value.base_version_id)
    fd.append('new_version_id', applyForm.value.new_version_id)
    fd.append('changelog_zh', applyForm.value.changelog_zh)
    const r = await api.post(`/datasets/${slug}/apply-corrections`, fd)
    if (r.data.generated === 'script') { downloadText(r.data.script, 'apply_corrections.do'); alert(r.data.note) }
    else alert(`已生成新版本 ${r.data.version_id}，应用 ${r.data.applied} 条勘误`)
    showApply.value = false; loadTab('versions'); reloadDetail()
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
function downloadText(text: string, name: string) {
  const blob = new Blob([text], { type: 'text/plain' })
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click()
}
// ---------- 数据处理配置（唯一ID + 脱敏规则）----------
const showDataCfg = ref(false); const dataCfg = ref<any>({ unique_id_var: '', script_only: false, variables: [] })
async function openDataCfg() { dataCfg.value = (await api.get(`/datasets/${slug}/data-config`)).data; showDataCfg.value = true }
async function saveDataCfg() {
  await api.put(`/datasets/${slug}/data-config`, {
    unique_id_var: dataCfg.value.unique_id_var, script_only: dataCfg.value.script_only,
    rules: dataCfg.value.variables.map((v: any) => ({ var_name: v.var_name, mask_action: v.mask_action, bucket_size: v.bucket_size }))
  })
  showDataCfg.value = false; reloadDetail()
}
// ---------- 批量勘误 ----------
function downloadTemplate() { window.open(`/api/datasets/${slug}/bug-template`, '_blank') }
const batchFile = ref<File | null>(null)
async function submitBatch() {
  if (!batchFile.value) { alert('请选择填好的模板文件'); return }
  const fd = new FormData(); fd.append('file', batchFile.value)
  try {
    const r = await api.post(`/datasets/${slug}/bugs/batch`, fd)
    alert(`已导入 ${r.data.items} 条修改，集成为一条勘误`); batchFile.value = null; loadTab('bugs')
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
// 逐条子项终审 / AI
async function finalizeItem(iid: number, adopt: string, score: number) {
  await api.post(`/bug-items/${iid}/finalize`, { adopt_level: adopt, final_score: score }); openBug(bugModal.value.id)
}
async function aiReviewItem(iid: number) { await api.post(`/bug-items/${iid}/ai-review`); openBug(bugModal.value.id) }
// ---------- 代码库版本/权限/评论 ----------
const codeVerForm = ref<any>({ version_label: '', changelog: '', source_code: '' }); const codeVerFile = ref<File | null>(null)
const codeComments = ref<any[]>([]); const codeCommentForm = ref<any>({ content: '', is_correction: false })
const showCodeVer = ref(false); const showCodeGrant = ref(false); const codeGrantForm = ref<any>({ user_id: null, can_edit: false, can_publish: true })
async function openCode(id: number) {
  codeModal.value = (await api.get(`/code/${id}`)).data
  codeComments.value = (await api.get(`/code/${id}/comments`)).data
}
async function publishCodeVer() {
  const fd = new FormData()
  fd.append('version_label', codeVerForm.value.version_label); fd.append('changelog', codeVerForm.value.changelog)
  if (codeVerFile.value) fd.append('file', codeVerFile.value); else fd.append('source_code', codeVerForm.value.source_code)
  try {
    await api.post(`/code/${codeModal.value.id}/versions`, fd)
    showCodeVer.value = false; codeVerForm.value = { version_label: '', changelog: '', source_code: '' }; codeVerFile.value = null
    openCode(codeModal.value.id)
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
function downloadCode(vid?: number) { window.open(`/api/code/${codeModal.value.id}/download${vid ? '?vid=' + vid : ''}`, '_blank') }
async function addCodeComment() {
  if (!codeCommentForm.value.content.trim()) return
  const fd = new FormData(); fd.append('content', codeCommentForm.value.content); fd.append('is_correction', String(codeCommentForm.value.is_correction))
  await api.post(`/code/${codeModal.value.id}/comments`, fd)
  codeCommentForm.value = { content: '', is_correction: false }; codeComments.value = (await api.get(`/code/${codeModal.value.id}/comments`)).data
}
async function grantCode() {
  const fd = new FormData(); fd.append('user_id', codeGrantForm.value.user_id)
  fd.append('can_edit', String(codeGrantForm.value.can_edit)); fd.append('can_publish', String(codeGrantForm.value.can_publish))
  try { await api.post(`/code/${codeModal.value.id}/grants`, fd); showCodeGrant.value = false; openCode(codeModal.value.id) }
  catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
function goDownloadTab() { loadTab('versions'); const el = document.getElementById('ds-tabs'); if (el) el.scrollIntoView({ behavior: 'smooth' }) }

async function setActFilter(k: string) {
  actFilter.value = k
  acts.value = (await api.get(`/datasets/${slug}/activity`, { params: { kind: k } })).data
}
async function submitPost() {
  if (!postForm.value.content_zh.trim()) return
  await api.post('/posts', { content_zh: postForm.value.content_zh, dataset_id: d.value.id,
                             visibility: 'platform', tags: [d.value.slug] })
  postForm.value.content_zh = ''; loadTab('feed')
}
const actColor = (x: string) => x === 'version' ? '#2d4a7c' : x === 'code' ? '#4b5563' : '#7c2d3a'
const actLabel = (x: string) => x === 'version' ? '版本' : x === 'code' ? '代码' : '勘误'

// ---------- bug ----------
async function submitBug() {
  try {
    const r = await api.post(`/datasets/${slug}/bugs`, bugForm.value)
    if (bugFile.value) {
      const fd = new FormData(); fd.append('file', bugFile.value)
      await api.post(`/bugs/${r.data.id}/attachments`, fd)
    }
    bugForm.value = { officer_id: '', variable_id: null, current_value: '', suggested_value: '', description_zh: '' }
    bugFile.value = null; loadTab('bugs')
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function openBug(id: number) { bugModal.value = (await api.get(`/bugs/${id}`)).data }
async function scoreBug(id: number, s: number) {
  await api.post(`/bugs/${id}/reviews`, { acceptability_score: s }); openBug(id)
}
async function aiReviewBug(id: number) { await api.post(`/bugs/${id}/ai-review`); openBug(id) }
async function finalizeBug(id: number, adopt: string, score: number) {
  await api.post(`/bugs/${id}/finalize`, { adopt_level: adopt, final_score: score })
  openBug(id); loadTab('bugs')
}

// ---------- version publish ----------
async function openPublish() {
  acceptedBugs.value = (await api.get(`/datasets/${slug}/bugs`)).data.filter((b: any) => b.status === 'accepted')
  pub.value = { version_id: '', changelog_zh: '', fixed: [], data_kind: 'raw' }; pubData.value = pubCode.value = null
  showPublish.value = true
}
async function doPublish() {
  try {
    const fd = new FormData()
    fd.append('version_id', pub.value.version_id)
    fd.append('changelog_zh', pub.value.changelog_zh)
    fd.append('data_kind', pub.value.data_kind || 'raw')
    fd.append('fixed_bug_ids', pub.value.fixed.join(','))
    if (pubData.value) fd.append('data_file', pubData.value)
    if (pubCode.value) fd.append('codebook_file', pubCode.value)
    await api.post(`/datasets/${slug}/versions`, fd)
    showPublish.value = false; loadTab('versions')
    d.value = (await api.get(`/datasets/${slug}`)).data
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
function download(v: any, file: string) {
  window.open(`/api/datasets/${slug}/versions/${v.id}/download?file=${file}`, '_blank')
}

// ---------- dataset edit ----------
function openEdit() {
  edit.value = { name_zh: d.value.name_zh, desc_zh: d.value.desc_zh,
    founder_contact: d.value.founder.contact, is_sensitive: d.value.is_sensitive }
  showEdit.value = true
}
async function doEdit() {
  await api.patch(`/datasets/${slug}`, edit.value)
  showEdit.value = false; d.value = (await api.get(`/datasets/${slug}`)).data
}
async function removeMember(uid: number) {
  if (!confirm('确认移除该成员？')) return
  await api.delete(`/datasets/${slug}/members/${uid}`)
  d.value = (await api.get(`/datasets/${slug}`)).data
}

// ---------- code ----------
async function addCode() {
  try {
    if (codeFile.value) {
      const fd = new FormData()
      fd.append('title_zh', codeAdd.value.title_zh); fd.append('lang', codeAdd.value.lang)
      fd.append('desc_zh', codeAdd.value.desc_zh); fd.append('file', codeFile.value)
      await api.post(`/datasets/${slug}/code/upload`, fd)
    } else {
      await api.post(`/datasets/${slug}/code`, codeAdd.value)
    }
    showCodeAdd.value = false; codeFile.value = null
    codeAdd.value = { title_zh: '', lang: 'Python', desc_zh: '', source_code: '' }; loadTab('code')
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function genWriteup(id: number) {
  const r = await api.post(`/code/${id}/writeup`); alert('已生成数据处理说明：\n\n' + r.data.body_zh)
}

// ---------- AI dashboard ----------
async function aiGen() {
  const r = await api.post(`/datasets/${slug}/analysis/generate`, null, { params: { prompt: aiPrompt.value } })
  aiCode.value = r.data.code
}
async function aiRun() {
  try { aiResult.value = (await api.post(`/datasets/${slug}/analysis/run`, null, { params: { code: aiCode.value } })).data }
  catch (e: any) { alert(e.response?.data?.detail || '失败') }
}

// ---------- literature ----------
async function addRef() {
  await api.post(`/datasets/${slug}/literature/refs`, litForm.value)
  litForm.value = { title: '', authors: '', venue: '', year: null, url: '', note_zh: '' }; loadTab('literature')
}
async function aiSummarize() {
  aiSummary.value = '生成中…'
  aiSummary.value = (await api.post(`/datasets/${slug}/literature/ai-summarize`)).data.summary
}
async function draftFromFlag(id: number) { await api.post(`/verify-flags/${id}/draft-bug`); loadTab('verify') }
const maxBar = (arr: any[]) => Math.max(...arr.map(a => +a.value), 1)
</script>

<template>
  <div v-if="d">
    <CharterModal scope="dataset" :refId="d.id" />

    <!-- 悬浮：下载最新数据 → 跳版本库 -->
    <button class="ds-download-fab" @click="goDownloadTab">
      <Icon name="data" class="ico" style="width:18px;height:18px" />
      <span>下载最新数据</span>
    </button>

    <div class="flex items-start justify-between">
      <div>
        <h1 class="text-2xl">{{ d.name_zh }}
          <span v-if="d.is_sensitive" class="tag border-accent2 text-accent2">敏感</span></h1>
        <p class="text-gray-500 mt-1">{{ d.desc_zh }}</p>
        <p class="text-sm mt-2">
          {{ t('ds.founder') }}：<router-link :to="`/users/${d.founder.id}`" class="text-accent hover:underline">{{ d.founder.name }}</router-link>
          · {{ t('ds.contact') }}：{{ d.founder.contact }}
        </p>
        <p class="text-sm mt-1 text-gray-500">
          <span class="text-gray-400">ID {{ d.id }}</span> ·
          <template v-if="d.group">{{ t('ds.groupOf') }}：<router-link :to="`/groups/${d.group.slug}`" class="text-accent hover:underline">{{ d.group.name_zh }}</router-link></template>
          <span v-else class="italic">{{ t('ds.standalone') }}</span>
        </p>
      </div>
      <div class="flex gap-2 flex-wrap justify-end">
        <span v-if="d.settings?.is_closed" class="tag border-accent2 text-accent2 self-center">已关闭</span>
        <button v-if="d.is_admin" class="btn-ghost" @click="openEdit">编辑数据集</button>
        <button v-if="d.is_admin" class="btn-ghost" @click="openSettings">数据集设置</button>
        <button v-if="d.is_admin" class="btn-ghost" @click="toggleClose">{{ d.settings?.is_closed ? '重新开放' : '关闭数据集' }}</button>
        <button v-if="!d.is_member && !d.settings?.is_closed" class="btn-ghost" @click="api.post(`/datasets/${slug}/join-requests`).then(()=>alert('已申请，等待管理员审批')).catch((e)=>alert(e.response?.data?.detail||'失败'))">
          {{ t('ds.joinProcess') }}
        </button>
      </div>
    </div>
    <p v-if="!d.is_member" class="text-xs text-accent2 mt-2 flex items-center gap-1">
      <Icon name="info" class="ico" style="width:14px;height:14px" /> {{ t('ds.notMemberTip') }}</p>
    <p v-if="d.is_member && !d.is_admin" class="text-xs text-gray-500 mt-2">
      当前下载策略：<b>{{ policyLabel[d.settings?.download_policy] || d.settings?.download_policy }}</b>。
      我的授权：<span v-if="(d.my_perms||[]).length"><span v-for="p in d.my_perms" :key="p" class="tag mr-1">{{ permLabel[p]||p }}</span></span><span v-else class="text-gray-400">暂无单独授权（加入数据集不等于获得下载权）</span>
    </p>

    <!-- 成员协作快捷条：核心协作动作一键直达 -->
    <div v-if="d.is_member" class="flex flex-wrap gap-2 mt-4">
      <button class="btn-ghost text-xs flex items-center gap-1.5" @click="loadTab('bugs')"><Icon name="edit" class="ico" style="width:15px;height:15px" /> {{ t('ds.submitBug') }}</button>
      <button class="btn-ghost text-xs flex items-center gap-1.5" @click="loadTab('code'); showCodeAdd=true"><Icon name="code" class="ico" style="width:15px;height:15px" /> {{ t('ds.code') }}</button>
      <button class="btn-ghost text-xs flex items-center gap-1.5" @click="loadTab('verify')"><Icon name="verify" class="ico" style="width:15px;height:15px" /> {{ t('ds.verify') }}</button>
      <button v-if="!d.is_admin && d.settings?.download_policy==='approval' && !canDownloadCurrent" class="btn-ghost text-xs flex items-center gap-1.5" @click="openDlReq"><Icon name="data" class="ico" style="width:15px;height:15px" /> 申请下载权限</button>
      <button v-if="canUploadCandidate" class="btn-ghost text-xs flex items-center gap-1.5" @click="showCand=true; loadCandidates()"><Icon name="publish" class="ico" style="width:15px;height:15px" /> 上传候选文件</button>
      <button v-if="d.is_admin" class="btn-ghost text-xs flex items-center gap-1.5" @click="loadTab('access')"><Icon name="users" class="ico" style="width:15px;height:15px" /> 成员与权限
        <span v-if="(mem.requests?.length||0)+(mem.download_requests?.length||0)>0" class="inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-accent2 text-white text-[10px]">{{ (mem.requests?.length||0)+(mem.download_requests?.length||0) }}</span>
      </button>
      <button v-if="d.is_admin" class="btn-primary text-xs flex items-center gap-1.5" @click="loadTab('versions'); openPublish()"><Icon name="publish" class="ico" style="width:15px;height:15px" /> {{ t('ds.publishVersion') }}</button>
    </div>

    <div id="ds-tabs" class="flex gap-1 border-b border-line mt-5 text-sm overflow-x-auto">
      <button v-for="[k,label] in tabs" :key="k" @click="loadTab(k)"
        :class="['px-3 py-2 whitespace-nowrap', tab===k?'border-b-2 border-accent text-accent':'text-gray-500']">
        {{ t(label) }}
      </button>
    </div>

    <div class="py-5">
      <!-- overview -->
      <div v-if="tab==='overview'">
        <div class="card">
          <div class="label-cap">{{ t('ds.currentVersion') }}</div>
          <p class="font-mono text-lg mt-1">{{ d.current_version?.version_id || '—' }}</p>
          <p class="text-sm text-gray-500 mt-1">{{ d.current_version?.changelog_zh }}</p>
        </div>
        <!-- 数据集公约（与课题组一致的展示位）-->
        <div v-if="d.charter" class="card mt-4">
          <div class="label-cap">数据集公约 · v{{ d.charter.version }}</div>
          <pre class="whitespace-pre-wrap bg-white text-ink border border-line mt-2">{{ d.charter.body_zh }}</pre>
          <button v-if="d.is_admin" class="btn-ghost text-xs mt-2" @click="openCharterEdit">编辑公约</button>
        </div>
        <div class="card mt-4">
          <div class="label-cap flex items-center gap-2">
            <button class="hover:text-accent" @click="showMembers=true">{{ t('ds.members') }}（{{ d.members?.length || 0 }}）</button>
            <span class="text-[11px] text-gray-400 normal-case">点击查看全部</span>
          </div>
          <table class="w-full text-sm mt-2">
            <tr v-for="m in (d.members||[]).slice(0,3)" :key="m.user_id" class="border-t border-line">
              <td class="py-1"><router-link :to="`/users/${m.user_id}`" class="text-accent hover:underline">{{ m.name }}</router-link>
                <span class="text-gray-400 text-xs ml-1">ID {{ m.user_id }}</span></td>
              <td><span class="tag" :class="m.is_lead ? 'border-accent text-accent' : ''">{{ roleLabel(m) }}</span></td>
              <td class="text-gray-400 text-xs">{{ m.joined_at?.slice(0,10) }}</td>
            </tr>
          </table>
          <button v-if="(d.members||[]).length>3" class="text-xs text-accent mt-2 hover:underline" @click="showMembers=true">查看全部 {{ d.members.length }} 名成员 →</button>
        </div>
        <div v-if="d.publications?.length" class="card mt-4">
          <div class="label-cap">近期刊物</div>
          <ul class="text-sm mt-2 space-y-1">
            <li v-for="p in d.publications" :key="p.title">
              <a v-if="p.url" :href="p.url" target="_blank" class="text-accent hover:underline">{{ p.title }} ↗</a>
              <span v-else>{{ p.title }}</span> · {{ p.venue }} ({{ p.year }})
            </li>
          </ul>
        </div>
      </div>

      <!-- activity 更新记录 -->
      <div v-else-if="tab==='activity'">
        <div class="flex gap-1 mb-4">
          <button v-for="[k,l] in [['all','ds.filterAll'],['version','ds.filterVersion'],['bug','ds.filterBug'],['code','ds.filterCode']]" :key="k"
            @click="setActFilter(k)"
            :class="['px-3 py-1 rounded text-xs border transition', actFilter===k ? 'bg-accent text-white border-accent' : 'border-line text-gray-500 bg-white hover:bg-paper']">
            {{ t(l) }}
          </button>
        </div>
        <div class="rounded-lg border border-line bg-white divide-y divide-line">
          <div v-for="(e,i) in acts" :key="i" class="px-4 py-3 flex items-start gap-3">
            <span class="dot mt-1.5" :style="{ background: actColor(e.type) }"></span>
            <div class="min-w-0 flex-1">
              <div class="text-sm text-gray-800">{{ e.title }}</div>
              <div v-if="e.detail" class="text-xs text-gray-500 mt-0.5 line-clamp-2">{{ e.detail }}</div>
            </div>
            <div class="text-xs text-gray-400 whitespace-nowrap">{{ actLabel(e.type) }}<span v-if="e.at"> · {{ (e.at||'').slice(0,10) }}</span></div>
          </div>
          <p v-if="!acts.length" class="px-4 py-4 text-gray-400 text-sm">{{ t('ds.noActivity') }}</p>
        </div>
      </div>

      <!-- dashboard -->
      <div v-else-if="tab==='dashboard'">
        <p class="text-xs text-gray-500 mb-3">看板与在线分析基于「派生汇总表」（不含原始个体数据）：df 有四列 var_name/group_key/bucket/value。分析代码在服务器的只读隔离子进程里运行，禁文件/网络/写操作，10 秒超时，绝不改原始数据。</p>
        <div class="card">
          <div class="label-cap">样本描述性统计 · gender（只读，从派生汇总出图）</div>
          <div class="mt-3 space-y-2">
            <div v-for="b in dash" :key="b.bucket" class="flex items-center gap-2 text-sm">
              <span class="w-16">{{ b.bucket }}</span>
              <div class="h-4 bg-accent rounded" :style="{ width: (240*+b.value/maxBar(dash))+'px' }"></div>
              <span class="font-mono text-xs">{{ b.value }}</span>
            </div>
          </div>
        </div>
        <div class="card mt-4">
          <div class="label-cap">AI / 手写描述分析（只读沙箱，绝不改原始值）</div>
          <template v-if="canAnalyze">
            <input v-model="aiPrompt" class="input mt-2" placeholder="用自然语言描述分析需求，如：统计各变量分布" />
            <div class="flex gap-2 mt-2">
              <button class="btn-ghost" @click="aiGen">AI 生成代码</button>
              <button class="btn-primary" @click="aiRun" :disabled="!aiCode">在沙箱运行</button>
            </div>
            <textarea v-model="aiCode" class="input mt-2 font-mono text-xs" rows="4" placeholder="生成/手写的 pandas 代码（result=...）"></textarea>
            <pre v-if="aiResult" class="mt-2">{{ JSON.stringify(aiResult, null, 2) }}</pre>
          </template>
          <p v-else class="text-sm text-gray-400 mt-2">在线分析功能需数据集管理员单独授权后开放。</p>
        </div>
      </div>

      <!-- versions -->
      <div v-else-if="tab==='versions'">
        <div v-if="d.is_admin" class="mb-3 flex flex-wrap gap-2">
          <button class="btn-primary" @click="openPublish">{{ t('ds.publishVersion') }}</button>
          <button class="btn-ghost" @click="openApply">一键应用已采纳勘误发版</button>
          <button class="btn-ghost" @click="openDataCfg">数据处理设置（唯一ID/脱敏规则）</button>
        </div>
        <p class="text-xs text-gray-500 mb-3">数据分类：<b>原始</b>与<b>脱敏</b>同步迭代（有当前推荐版）；<b>样例</b>公开可下、独立不迭代。</p>
        <div v-for="v in versions" :key="v.id" class="card mb-3 flex items-center justify-between">
          <div>
            <span class="font-mono">{{ v.version_id }}</span>
            <span class="tag ml-2 border" :class="kindColor[v.data_kind]||''">{{ kindLabel[v.data_kind]||'原始数据' }}</span>
            <span v-if="v.is_current" class="tag ml-1">当前</span>
            <span v-if="v.based_on" class="text-xs text-gray-400 ml-2">基于 {{ v.based_on }}</span>
            <span v-if="v.masked_source" class="text-xs text-gray-400 ml-1">（脱敏自 {{ v.masked_source }}）</span>
            <p class="text-sm text-gray-500 mt-1">{{ v.changelog_zh }}</p>
          </div>
          <div class="flex gap-2 items-center flex-wrap justify-end">
            <button v-if="v.data_kind==='raw' && d.is_admin" class="btn-ghost text-xs" @click="openDesens(v)">生成脱敏版</button>
            <button class="btn-ghost text-xs" @click="download(v,'codebook')">Codebook</button>
            <button v-if="!v.has_data" class="text-xs text-gray-400">无数据文件</button>
            <button v-else-if="v.data_kind==='sample' || d.is_admin || (v.is_current ? canDownloadCurrent : (d.settings?.history_downloadable || (d.my_perms||[]).includes('download.history')))"
              class="btn-ghost text-xs" @click="download(v,'data')">下载 .dta</button>
            <button v-else-if="d.is_member && v.is_current && d.settings?.download_policy==='approval'"
              class="btn-ghost text-xs text-accent" @click="openDlReq">申请下载</button>
            <span v-else class="text-xs text-gray-400">无下载权限</span>
          </div>
        </div>
        <p v-if="d.is_member && !d.is_admin" class="text-xs text-gray-400 mb-2">下载权限由数据集管理员单独授予；样例数据所有登录用户可下。</p>
        <p v-if="!versions.length" class="text-gray-400 text-sm">暂无版本。</p>
      </div>

      <!-- bugs -->
      <div v-else-if="tab==='bugs'">
        <!-- 批量勘误 -->
        <div v-if="d.is_member" class="card mb-4">
          <div class="label-cap mb-2">批量勘误（Excel/CSV 一次多条，集成为一条勘误）</div>
          <p class="text-xs text-gray-500 mb-2">先下载模板，按「唯一ID值/变量名/当前值/建议值/说明与证据」填写；导入后系统按行拆分，逐条打分与终审。</p>
          <div class="flex flex-wrap items-center gap-2">
            <button class="btn-ghost text-xs" @click="downloadTemplate">下载批量模板</button>
            <input type="file" accept=".xlsx,.csv" @change="(e:any)=>batchFile=e.target.files[0]" class="text-xs" />
            <button class="btn-primary text-xs" @click="submitBatch">导入批量勘误</button>
          </div>
        </div>
        <div v-if="d.is_member" class="card mb-4">
          <div class="label-cap mb-2">{{ t('ds.submitBug') }}（单条）</div>
          <div class="grid grid-cols-2 gap-2">
            <input v-model="bugForm.officer_id" class="input" :placeholder="d.unique_id_var ? (d.unique_id_var + '（唯一ID）') : '唯一ID（管理员未设置）'" />
            <select v-model="bugForm.variable_id" class="input">
              <option :value="null">选择变量</option>
              <option v-for="v in vars" :key="v.id" :value="v.id">{{ v.var_name }}</option>
            </select>
            <input v-model="bugForm.current_value" class="input" placeholder="当前值" />
            <input v-model="bugForm.suggested_value" class="input" placeholder="建议值" />
          </div>
          <p class="text-[11px] text-gray-400 mt-1">第一格为唯一ID：{{ d.unique_id_var || '（管理员可在版本库·数据处理设置中指定）' }}，唯一ID本身不可修改。</p>
          <textarea v-model="bugForm.description_zh" class="input mt-2" placeholder="说明与证据"></textarea>
          <div class="flex items-center gap-2 mt-2">
            <input type="file" @change="(e:any)=>bugFile=e.target.files[0]" class="text-xs" />
            <button class="btn-primary ml-auto" @click="submitBug">{{ t('common.submit') }}</button>
          </div>
        </div>
        <div v-for="b in bugs" :key="b.id" class="card mb-2 flex items-center justify-between cursor-pointer" @click="openBug(b.id)">
          <div class="text-sm">
            <span class="font-mono text-xs">{{ b.officer_id }}</span> · {{ b.description_zh }}
            <span class="text-gray-400">（{{ b.current_value }} → {{ b.suggested_value }}）</span>
          </div>
          <span class="tag">{{ b.status }}</span>
        </div>
        <p v-if="!bugs.length" class="text-gray-400 text-sm">暂无勘误。评分制审核：成员评分+AI评分→管理员终审。</p>
      </div>

      <!-- code -->
      <div v-else-if="tab==='code'">
        <div v-if="d.is_member" class="mb-3"><button class="btn-primary" @click="showCodeAdd=true">＋提交代码</button></div>
        <div v-for="c in codes" :key="c.id" class="card mb-2 cursor-pointer" @click="openCode(c.id)">
          <div class="flex items-center justify-between">
            <span class="font-mono text-sm">{{ c.filename }} <span class="tag ml-1">{{ c.lang }}</span></span>
            <span class="text-xs text-gray-400">复用 {{ c.reuse_count }}</span>
          </div>
          <p class="text-sm text-gray-500 mt-1">{{ c.title_zh }}</p>
        </div>
        <p v-if="!codes.length" class="text-gray-400 text-sm">暂无处理代码。</p>
      </div>

      <!-- literature -->
      <div v-else-if="tab==='literature'">
        <div class="card">
          <div class="flex items-center justify-between">
            <div class="label-cap">重点文献清单</div>
            <button v-if="d.is_member" class="btn-ghost text-xs" @click="aiSummarize">AI 总结研究用途/话题</button>
          </div>
          <pre v-if="aiSummary" class="whitespace-pre-wrap bg-paper text-ink border border-line mt-2">{{ aiSummary }}</pre>
          <ul class="text-sm mt-2 space-y-1">
            <li v-for="r in lit.refs" :key="r.id">
              <a v-if="r.url" :href="r.url" target="_blank" class="text-accent hover:underline">{{ r.title }} ↗</a>
              <span v-else>{{ r.title }}</span> · {{ r.authors }} · {{ r.venue }} ({{ r.year }})
            </li>
          </ul>
          <p v-if="!lit.refs.length" class="text-gray-400 text-sm">暂无文献。</p>
        </div>
        <div v-if="d.is_member" class="card mt-3">
          <div class="label-cap mb-2">添加重点文献</div>
          <div class="grid grid-cols-2 gap-2">
            <input v-model="litForm.title" class="input" placeholder="标题" />
            <input v-model="litForm.authors" class="input" placeholder="作者" />
            <input v-model="litForm.venue" class="input" placeholder="刊物" />
            <input v-model.number="litForm.year" class="input" placeholder="年份" />
            <input v-model="litForm.url" class="input col-span-2" placeholder="链接 URL（可点击跳转）" />
          </div>
          <button class="btn-primary mt-2" @click="addRef">添加</button>
        </div>
      </div>

      <!-- feed 研究广场（该数据集相关讨论） -->
      <div v-else-if="tab==='feed'">
        <div v-if="d.is_member" class="card mb-4">
          <textarea v-model="postForm.content_zh" class="input" :placeholder="t('ds.postHere')"></textarea>
          <div class="flex justify-end mt-2"><button class="btn-primary text-sm" @click="submitPost">{{ t('feed.post') }}</button></div>
        </div>
        <div v-for="p in posts" :key="p.id" class="card mb-2">
          <div class="flex items-center gap-2 text-sm">
            <router-link :to="`/users/${p.author_id}`" class="text-accent hover:underline">{{ p.author_name }}</router-link>
          </div>
          <p class="mt-1 text-sm">{{ p.content_zh }}</p>
          <div class="mt-2 flex gap-1"><span v-for="tg in p.tags" :key="tg" class="tag">{{ tg }}</span></div>
        </div>
        <p v-if="!posts.length" class="text-gray-400 text-sm">{{ t('ds.noPosts') }}</p>
      </div>

      <!-- access 成员与权限（仅管理员） -->
      <div v-else-if="tab==='access'">
        <!-- 加入申请 -->
        <div class="card mb-4">
          <div class="label-cap mb-2">加入申请审批</div>
          <div v-for="r in mem.requests" :key="r.id" class="flex items-center gap-2 text-sm border-t border-line py-2">
            <router-link :to="`/users/${r.user_id}`" class="text-accent hover:underline">{{ r.name }}</router-link>
            <span class="text-gray-400 truncate">{{ r.message }}</span>
            <div class="ml-auto flex gap-2">
              <button class="btn-primary text-xs" @click="decideJoin(r.id,true)">通过</button>
              <button class="btn-ghost text-xs" @click="decideJoin(r.id,false)">拒绝</button>
            </div>
          </div>
          <p v-if="!mem.requests?.length" class="text-gray-400 text-sm">暂无待审批的加入申请。</p>
        </div>
        <!-- 下载申请 -->
        <div class="card mb-4">
          <div class="label-cap mb-2">下载申请审批</div>
          <div v-for="r in mem.download_requests" :key="r.id" class="border-t border-line py-2 text-sm">
            <div class="flex items-center gap-2">
              <router-link :to="`/users/${r.user_id}`" class="text-accent hover:underline">{{ r.name }}</router-link>
              <span class="text-gray-400">版本 {{ r.scope_version || '当前' }}</span>
              <span v-if="r.share_with_others" class="tag">拟共享</span>
              <div class="ml-auto flex gap-2">
                <button class="btn-primary text-xs" @click="decideDownload(r.id,true)">批准</button>
                <button class="btn-ghost text-xs" @click="decideDownload(r.id,false)">拒绝</button>
              </div>
            </div>
            <p class="text-gray-500 mt-1">用途：{{ r.purpose }}<span v-if="r.planned_until"> · 预计使用至 {{ r.planned_until }}</span></p>
          </div>
          <p v-if="!mem.download_requests?.length" class="text-gray-400 text-sm">暂无待审批的下载申请。</p>
        </div>
        <!-- 成员列表 + 授权 -->
        <div class="card">
          <div class="label-cap mb-2">成员与单独授权</div>
          <p class="text-xs text-gray-400 mb-2">授权由任一管理员操作；设置/取消管理员与转让总管理员仅「总管理员」可操作。</p>
          <div v-for="m in mem.members" :key="m.user_id" class="border-t border-line py-2 text-sm">
            <div class="flex items-center gap-2 flex-wrap">
              <router-link :to="`/users/${m.user_id}`" class="text-accent hover:underline">{{ m.name }}</router-link>
              <span class="text-gray-400 text-xs">ID {{ m.user_id }}</span>
              <span class="tag" :class="m.is_lead ? 'border-accent text-accent' : ''">{{ roleLabel(m) }}</span>
              <div class="ml-auto flex gap-2 flex-wrap">
                <button v-if="!m.is_admin" class="btn-ghost text-xs" @click="openGrant(m)">授权</button>
                <!-- 设置/取消管理员、转让：仅总管理员 -->
                <template v-if="mem.is_lead && !m.is_lead">
                  <button v-if="!m.is_admin" class="btn-ghost text-xs" @click="addAdmin(m.user_id)">设为管理员</button>
                  <button v-else class="btn-ghost text-xs" @click="removeAdmin(m.user_id)">取消管理员</button>
                  <button class="btn-ghost text-xs" @click="transferLead(m.user_id)">转让总管理员</button>
                </template>
                <!-- 移除普通成员：任一管理员可操作；管理员的移除留给总管理员 -->
                <button v-if="!m.is_lead && (!m.is_admin || mem.is_lead)" class="text-xs text-accent2" @click="removeDsMember(m.user_id)">移除</button>
              </div>
            </div>
            <div v-if="m.perms?.length" class="mt-1 flex flex-wrap gap-1">
              <span v-for="p in m.perms" :key="p" class="tag flex items-center gap-1">
                {{ permLabel[p]||p }}
                <button class="text-accent2" @click="revokePerm(m.user_id,p)">×</button>
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- verify -->
      <div v-else-if="tab==='verify'">
        <p class="text-xs text-gray-500 mb-3">规则/AI 只发现与起草，绝不静默改原始数据；一键生成勘误草稿走评分制审核。</p>
        <div v-for="f in flags" :key="f.id" class="card mb-2 flex items-center justify-between">
          <div class="text-sm">
            <span class="tag">{{ f.source }}</span> {{ f.variable_name }} · {{ f.issue_desc }}
            <span class="text-gray-400 text-xs">conf={{ f.confidence }}</span>
          </div>
          <button v-if="f.status==='open' && d.is_member" class="btn-ghost text-xs" @click="draftFromFlag(f.id)">一键生成勘误草稿</button>
          <span v-else class="tag">{{ f.status }}</span>
        </div>
        <p v-if="!flags.length" class="text-gray-400 text-sm">暂无核验标记。</p>
      </div>
    </div>

    <!-- ========== 弹窗 ========== -->
    <!-- bug 详情 -->
    <div v-if="bugModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="bugModal=null">
      <div class="bg-white rounded-lg max-w-lg w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <div class="flex items-center justify-between">
          <h3 class="text-lg">勘误 #{{ bugModal.id }} <span class="tag ml-1">{{ bugModal.status }}</span></h3>
          <button @click="bugModal=null" class="text-gray-400">×</button>
        </div>
        <p class="text-sm mt-2">提交人：<router-link :to="`/users/${bugModal.reporter.id}`" class="text-accent">{{ bugModal.reporter.name }}</router-link></p>
        <p class="text-sm mt-1">{{ bugModal.description_zh }}</p>
        <p v-if="bugModal.fixed_in_version" class="text-xs text-accent mt-1">已在版本 {{ bugModal.fixed_in_version }} 修复</p>

        <!-- 逐条修改项（批量或单条统一按子项确认）-->
        <div v-if="bugModal.items?.length" class="mt-3 border-t border-line pt-3">
          <div class="label-cap mb-1">修改项（逐条打分与终审，共 {{ bugModal.items.length }} 条）</div>
          <div v-for="it in bugModal.items" :key="it.id" class="border border-line rounded p-2 mb-2 text-sm">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-mono text-xs">{{ it.uid_value }}</span>
              <span class="text-gray-500">{{ it.var_name }}：{{ it.current_value }} → <b>{{ it.suggested_value }}</b></span>
              <span class="tag ml-auto">{{ it.status }}</span>
            </div>
            <p v-if="it.reason" class="text-xs text-gray-500 mt-1">{{ it.reason }}</p>
            <div class="flex items-center gap-2 mt-1 flex-wrap">
              <span v-if="it.ai_score!=null" class="text-xs text-gray-400">AI {{ it.ai_score }}/10</span>
              <span v-if="it.final_score!=null" class="text-xs text-accent">终审 {{ it.final_score }}/10（{{ it.adopt_level }}）</span>
              <template v-if="d.is_admin && it.status==='pending'">
                <button class="btn-ghost text-[11px]" @click="aiReviewItem(it.id)">AI评分</button>
                <button class="btn-primary text-[11px]" @click="finalizeItem(it.id,'full',9)">采纳(9)</button>
                <button class="btn-ghost text-[11px]" @click="finalizeItem(it.id,'partial',6)">部分(6)</button>
                <button class="btn-ghost text-[11px]" @click="finalizeItem(it.id,'reject',0)">拒绝</button>
              </template>
            </div>
          </div>
          <p class="text-[11px] text-gray-400">采纳后可在版本库「一键应用已采纳勘误发版」，按唯一ID自动改上一版数据。</p>
        </div>
        <div v-if="bugModal.attachments.length" class="mt-2">
          <div class="label-cap">证据附件</div>
          <a v-for="a in bugModal.attachments" :key="a.id" :href="`/api/bug-attachments/${a.id}/download`" target="_blank" class="text-accent text-xs flex items-center gap-1 hover:underline"><Icon name="clip" class="ico" style="width:13px;height:13px" /> {{ a.file_name }}</a>
        </div>
        <div class="mt-3 border-t border-line pt-3">
          <div class="label-cap">评审记录</div>
          <div v-for="(r,i) in bugModal.reviews" :key="i" class="text-sm flex gap-2">
            <span class="tag">{{ r.reviewer_type }}</span><span class="font-mono">{{ r.score }}/10</span><span class="text-gray-400">{{ r.comment }}</span>
          </div>
          <div v-if="bugModal.final" class="text-sm mt-1 text-accent">终审：{{ bugModal.final.adopt_level }} · {{ bugModal.final.final_score }}/10</div>
        </div>
        <div v-if="d.is_member && bugModal.status==='pending'" class="mt-3 border-t border-line pt-3">
          <div class="label-cap mb-1">我来评分（0-10）</div>
          <div class="flex gap-1 flex-wrap">
            <button v-for="s in [0,2,4,6,8,10]" :key="s" class="btn-ghost text-xs" @click="scoreBug(bugModal.id, s)">{{ s }}</button>
            <button class="btn-ghost text-xs" @click="aiReviewBug(bugModal.id)">触发 AI 评分</button>
          </div>
        </div>
        <div v-if="d.is_admin && bugModal.status==='pending'" class="mt-3 border-t border-line pt-3">
          <div class="label-cap mb-1">终审（管理员）</div>
          <div class="flex gap-1">
            <button class="btn-primary text-xs" @click="finalizeBug(bugModal.id,'full',9)">全部采纳(9)</button>
            <button class="btn-ghost text-xs" @click="finalizeBug(bugModal.id,'partial',6)">部分采纳(6)</button>
            <button class="btn-ghost text-xs" @click="finalizeBug(bugModal.id,'reject',0)">不采纳</button>
          </div>
        </div>
      </div>
    </div>

    <!-- code 详情 -->
    <div v-if="codeModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="codeModal=null">
      <div class="bg-white rounded-lg max-w-2xl w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-mono">{{ codeModal.filename }}</h3>
          <button @click="codeModal=null" class="text-gray-400">×</button>
        </div>
        <p class="text-sm text-gray-500 mt-1">{{ codeModal.title_zh }} · {{ codeModal.desc_zh }}
          <span class="text-gray-400">· 作者 {{ codeModal.author_name }}</span></p>
        <div class="flex flex-wrap gap-2 mt-2">
          <button v-if="codeModal.is_member" class="btn-ghost text-xs" @click="downloadCode()">下载代码文件</button>
          <button v-if="codeModal.can_publish" class="btn-ghost text-xs" @click="showCodeVer=true">发布新版本</button>
          <button v-if="codeModal.can_grant" class="btn-ghost text-xs" @click="showCodeGrant=true">授予权限</button>
          <button v-if="d.is_member" class="btn-ghost text-xs" @click="genWriteup(codeModal.id)">AI 生成处理说明</button>
        </div>
        <pre class="mt-2">{{ codeModal.source_code }}</pre>

        <!-- 版本迭代 -->
        <div v-if="codeModal.versions?.length" class="mt-3 border-t border-line pt-3">
          <div class="label-cap mb-1">版本迭代</div>
          <div v-for="v in codeModal.versions" :key="v.id" class="text-sm flex items-center gap-2 border-t border-line py-1">
            <span class="font-mono text-xs">{{ v.version_label }}</span>
            <span v-if="v.is_current" class="tag">当前</span>
            <span class="text-gray-500 truncate">{{ v.changelog }}</span>
            <span class="text-gray-400 text-xs ml-auto">{{ v.created_at }}</span>
            <button v-if="codeModal.is_member" class="btn-ghost text-[11px]" @click="downloadCode(v.id)">下载</button>
          </div>
        </div>

        <!-- 评论（可选勘误类）-->
        <div class="mt-3 border-t border-line pt-3">
          <div class="label-cap mb-1">评论</div>
          <div v-for="c in codeComments" :key="c.id" class="text-sm border-t border-line py-1">
            <router-link :to="`/users/${c.user_id}`" class="text-accent hover:underline">{{ c.name }}</router-link>
            <span v-if="c.is_correction" class="tag border-accent2 text-accent2 ml-1">勘误</span>
            <span class="text-gray-400 text-xs ml-1">{{ c.created_at }}</span>
            <p class="text-gray-600">{{ c.content }}</p>
          </div>
          <div v-if="codeModal.is_member" class="mt-2">
            <textarea v-model="codeCommentForm.content" class="input text-sm" rows="2" placeholder="写评论"></textarea>
            <div class="flex items-center gap-2 mt-1">
              <label class="text-xs flex items-center gap-1"><input type="checkbox" v-model="codeCommentForm.is_correction" /> 标记为勘误类评论（指出代码问题）</label>
              <button class="btn-primary text-xs ml-auto" @click="addCodeComment">发表</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 发布代码新版本 -->
    <div v-if="showCodeVer" class="fixed inset-0 bg-black/40 flex items-center justify-center z-[60]" @click.self="showCodeVer=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-3">发布代码新版本</h3>
        <input v-model="codeVerForm.version_label" class="input mb-2 font-mono" placeholder="版本号，如 v2" />
        <textarea v-model="codeVerForm.changelog" class="input mb-2" placeholder="本次修改内容（必填）"></textarea>
        <label class="label-cap">上传新代码文件（或下方粘贴）</label>
        <input type="file" @change="(e:any)=>codeVerFile=e.target.files[0]" class="text-xs mb-2 block" />
        <textarea v-model="codeVerForm.source_code" class="input font-mono text-xs" rows="4" placeholder="粘贴新代码（上传文件时可留空）"></textarea>
        <div class="flex justify-end gap-2 mt-3">
          <button class="btn-ghost" @click="showCodeVer=false">取消</button>
          <button class="btn-primary" @click="publishCodeVer">发布</button>
        </div>
      </div>
    </div>

    <!-- 授予代码权限 -->
    <div v-if="showCodeGrant" class="fixed inset-0 bg-black/40 flex items-center justify-center z-[60]" @click.self="showCodeGrant=false">
      <div class="bg-white rounded-lg max-w-sm w-full p-6 m-4">
        <h3 class="text-lg mb-3">授予代码权限</h3>
        <input v-model.number="codeGrantForm.user_id" type="number" class="input mb-2" placeholder="成员用户 ID" />
        <label class="flex items-center gap-2 text-sm mb-1"><input type="checkbox" v-model="codeGrantForm.can_edit" /> 可修改</label>
        <label class="flex items-center gap-2 text-sm mb-3"><input type="checkbox" v-model="codeGrantForm.can_publish" /> 可重新发布版本</label>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showCodeGrant=false">取消</button>
          <button class="btn-primary" @click="grantCode">授予</button>
        </div>
      </div>
    </div>

    <!-- 发布版本 -->
    <div v-if="showPublish" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showPublish=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <h3 class="text-lg mb-3">发布新版本（旧版本保留、不可覆盖）</h3>
        <input v-model="pub.version_id" class="input mb-2 font-mono" placeholder="版本号，如 v1.1.0 / v1.0.1-hotfix" />
        <label class="label-cap">数据分类</label>
        <select v-model="pub.data_kind" class="input mb-2">
          <option value="raw">原始数据（与脱敏同步迭代）</option>
          <option value="masked">脱敏数据（与原始同步迭代）</option>
          <option value="sample">样例数据（公开可下、独立不迭代）</option>
        </select>
        <textarea v-model="pub.changelog_zh" class="input mb-2" placeholder="更新说明 changelog"></textarea>
        <label class="label-cap">数据文件 (.dta)</label>
        <input type="file" accept=".dta" @change="(e:any)=>pubData=e.target.files[0]" class="text-xs mb-2 block" />
        <label class="label-cap">Codebook (PDF/DOCX)</label>
        <input type="file" @change="(e:any)=>pubCode=e.target.files[0]" class="text-xs mb-2 block" />
        <div v-if="acceptedBugs.length" class="mt-2">
          <div class="label-cap mb-1">本次修复的已采纳勘误（勾选→标 fixed）</div>
          <label v-for="b in acceptedBugs" :key="b.id" class="flex items-center gap-2 text-sm">
            <input type="checkbox" :value="b.id" v-model="pub.fixed" /> #{{ b.id }} {{ b.description_zh }}
          </label>
        </div>
        <div class="flex justify-end gap-2 mt-3">
          <button class="btn-ghost" @click="showPublish=false">取消</button>
          <button class="btn-primary" @click="doPublish">发布</button>
        </div>
      </div>
    </div>

    <!-- 编辑数据集 -->
    <div v-if="showEdit" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showEdit=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-3">编辑数据集</h3>
        <input v-model="edit.name_zh" class="input mb-2" placeholder="名称" />
        <textarea v-model="edit.desc_zh" class="input mb-2" placeholder="简介"></textarea>
        <input v-model="edit.founder_contact" class="input mb-2" placeholder="发起人联系方式" />
        <label class="flex items-center gap-2 text-sm mb-3"><input type="checkbox" v-model="edit.is_sensitive" /> 标记为敏感数据集</label>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showEdit=false">取消</button>
          <button class="btn-primary" @click="doEdit">保存</button>
        </div>
      </div>
    </div>

    <!-- 提交代码 -->
    <div v-if="showCodeAdd" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showCodeAdd=false">
      <div class="bg-white rounded-lg max-w-lg w-full p-6 m-4">
        <h3 class="text-lg mb-3">提交处理代码</h3>
        <div class="flex gap-2 mb-2">
          <input v-model="codeAdd.title_zh" class="input" placeholder="标题" />
          <select v-model="codeAdd.lang" class="input w-32"><option>Stata</option><option>Python</option><option>R</option></select>
        </div>
        <input v-model="codeAdd.desc_zh" class="input mb-2" placeholder="说明" />
        <label class="label-cap">方式一：上传代码文件</label>
        <input type="file" @change="(e:any)=>codeFile=e.target.files[0]" class="text-xs mb-2 block" />
        <label class="label-cap">方式二：直接粘贴代码</label>
        <textarea v-model="codeAdd.source_code" class="input font-mono text-xs" rows="5" placeholder="粘贴代码（上传文件时可留空）"></textarea>
        <div class="flex justify-end gap-2 mt-3">
          <button class="btn-ghost" @click="showCodeAdd=false">取消</button>
          <button class="btn-primary" @click="addCode">提交</button>
        </div>
      </div>
    </div>

    <!-- 下载申请（成员）-->
    <div v-if="showDlReq" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showDlReq=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <h3 class="text-lg mb-3">申请数据下载权限</h3>
        <label class="label-cap">研究用途（必填）</label>
        <textarea v-model="dlReq.purpose" class="input mb-2" placeholder="说明数据将用于什么研究"></textarea>
        <label class="label-cap">数据版本</label>
        <input v-model="dlReq.scope_version" class="input mb-2 font-mono" placeholder="如 v1.0.0" />
        <label class="label-cap">预计使用时间</label>
        <input v-model="dlReq.planned_until" class="input mb-2" placeholder="如 2026-12" />
        <label class="flex items-center gap-2 text-sm mb-2"><input type="checkbox" v-model="dlReq.share_with_others" /> 可能与他人共享</label>
        <label class="flex items-center gap-2 text-sm mb-3"><input type="checkbox" v-model="dlReq.agree_charter" /> 我已阅读并同意数据使用公约</label>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showDlReq=false">取消</button>
          <button class="btn-primary" :disabled="!dlReq.agree_charter" @click="submitDlReq">提交申请</button>
        </div>
      </div>
    </div>

    <!-- 授予单独授权（管理员）-->
    <div v-if="showGrant" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showGrant=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-1">授予单独授权</h3>
        <p class="text-xs text-gray-500 mb-3">给「{{ grantTarget?.name }}」授予一项权限（加入数据集不自动获得，需在此单独授予）。</p>
        <label class="label-cap">授权项</label>
        <select v-model="grantForm.perm" class="input mb-2">
          <option v-for="c in mem.grant_catalog" :key="c.perm" :value="c.perm">{{ c.label }}</option>
        </select>
        <label class="label-cap">有效范围</label>
        <select v-model="grantForm.scope_type" class="input mb-2">
          <option value="permanent">永久有效</option>
          <option value="until_date">指定日期前有效</option>
          <option value="version">仅对指定版本有效</option>
          <option value="project">仅用于指定研究项目</option>
        </select>
        <input v-if="grantForm.scope_type==='until_date'" v-model="grantForm.valid_to" class="input mb-2" placeholder="有效期 YYYY-MM-DD" />
        <input v-if="grantForm.scope_type==='version'" v-model="grantForm.scope_version" class="input mb-2 font-mono" placeholder="版本号 如 v1.0.0" />
        <input v-if="grantForm.scope_type==='project'" v-model="grantForm.project_note" class="input mb-2" placeholder="研究项目名称" />
        <div class="flex justify-end gap-2 mt-2">
          <button class="btn-ghost" @click="showGrant=false">取消</button>
          <button class="btn-primary" @click="doGrant">授予</button>
        </div>
      </div>
    </div>

    <!-- 数据集设置（管理员）-->
    <div v-if="showSettings" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showSettings=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <h3 class="text-lg mb-3">数据集设置</h3>
        <label class="label-cap">下载策略</label>
        <select v-model="settingsForm.download_policy" class="input mb-3">
          <option value="public">公开数据（登录可下）</option>
          <option value="member">成员可下载</option>
          <option value="approval">审批后下载</option>
          <option value="masked_only">仅脱敏数据可下载</option>
          <option value="forbidden">禁止下载（仅在线分析）</option>
        </select>
        <label class="flex items-center gap-2 text-sm mb-2"><input type="checkbox" v-model="settingsForm.history_visible" /> 成员默认可见历史版本信息</label>
        <label class="flex items-center gap-2 text-sm mb-2"><input type="checkbox" v-model="settingsForm.history_downloadable" /> 成员默认可下载历史版本</label>
        <label class="flex items-center gap-2 text-sm mb-2"><input type="checkbox" v-model="settingsForm.analysis_open" /> 在线分析对全体成员开放</label>
        <label class="flex items-center gap-2 text-sm mb-2"><input type="checkbox" v-model="settingsForm.codebook_public" /> 公开 codebook 非成员可见</label>
        <label class="flex items-center gap-2 text-sm mb-3"><input type="checkbox" v-model="settingsForm.dashboard_public" /> 公开看板非成员可见</label>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showSettings=false">取消</button>
          <button class="btn-primary" @click="saveSettings">保存</button>
        </div>
      </div>
    </div>

    <!-- 编辑数据集公约 -->
    <div v-if="showCharterEdit" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showCharterEdit=false">
      <div class="bg-white rounded-lg max-w-lg w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <h3 class="text-lg mb-1">编辑数据集公约</h3>
        <p class="text-xs text-gray-500 mb-3">保存后版本号 +1，成员需重新确认。</p>
        <textarea v-model="charterForm.body_zh" class="input font-mono text-sm" rows="10"></textarea>
        <div class="flex justify-end gap-2 mt-3">
          <button class="btn-ghost" @click="showCharterEdit=false">取消</button>
          <button class="btn-primary" @click="saveCharter">保存</button>
        </div>
      </div>
    </div>

    <!-- 上传候选文件 -->
    <div v-if="showCand" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showCand=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <h3 class="text-lg mb-1">上传版本候选文件</h3>
        <p class="text-xs text-gray-500 mb-3">候选文件供数据集管理员审阅后正式发版；候选不等于正式版本。</p>
        <input type="file" @change="(e:any)=>candFile=e.target.files[0]" class="text-xs mb-2 block" />
        <textarea v-model="candNote" class="input mb-2" placeholder="说明（可选）"></textarea>
        <div v-if="candidates.length" class="mt-2">
          <div class="label-cap mb-1">已上传候选</div>
          <div v-for="c in candidates" :key="c.id" class="text-xs text-gray-500 border-t border-line py-1">{{ c.file_name }} · {{ c.status }}</div>
        </div>
        <div class="flex justify-end gap-2 mt-3">
          <button class="btn-ghost" @click="showCand=false">取消</button>
          <button class="btn-primary" @click="uploadCandidate">上传</button>
        </div>
      </div>
    </div>

    <!-- 一键生成脱敏版 -->
    <div v-if="showDesens" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showDesens=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-1">从「{{ desensForm.from?.version_id }}」生成脱敏版</h3>
        <p class="text-xs text-gray-500 mb-3">按「数据处理设置」里的脱敏规则处理。数据不大将在服务器直接生成；否则返回脚本供本地运行。</p>
        <input v-model="desensForm.new_version_id" class="input mb-2 font-mono" placeholder="脱敏版本号，如 v1.0.0-masked" />
        <textarea v-model="desensForm.changelog_zh" class="input mb-2" placeholder="说明（可留空）"></textarea>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showDesens=false">取消</button>
          <button class="btn-primary" @click="doDesensitize">生成</button>
        </div>
      </div>
    </div>

    <!-- 一键应用已采纳勘误发版 -->
    <div v-if="showApply" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showApply=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-1">应用已采纳勘误 → 生成新版本</h3>
        <p class="text-xs text-gray-500 mb-3">按唯一ID+变量名定位单元格，自动改上一版数据。需先在「数据处理设置」指定唯一ID。数据过大将回退为脚本。</p>
        <label class="label-cap">基准版本</label>
        <select v-model="applyForm.base_version_id" class="input mb-2">
          <option v-for="v in versions.filter(x=>x.has_data)" :key="v.id" :value="v.id">{{ v.version_id }}（{{ kindLabel[v.data_kind] }}）</option>
        </select>
        <input v-model="applyForm.new_version_id" class="input mb-2 font-mono" placeholder="新版本号，如 v1.1.0" />
        <textarea v-model="applyForm.changelog_zh" class="input mb-2" placeholder="更新说明（可留空，自动记录应用条数）"></textarea>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showApply=false">取消</button>
          <button class="btn-primary" @click="doApply">应用并发版</button>
        </div>
      </div>
    </div>

    <!-- 数据处理设置：唯一ID + 脱敏规则 -->
    <div v-if="showDataCfg" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showDataCfg=false">
      <div class="bg-white rounded-lg max-w-lg w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <h3 class="text-lg mb-1">数据处理设置</h3>
        <p class="text-xs text-gray-500 mb-3">唯一ID用于批量勘误定位记录（其本身不可修改）；脱敏规则用于一键生成脱敏版。</p>
        <label class="label-cap">唯一ID变量</label>
        <select v-model="dataCfg.unique_id_var" class="input mb-2">
          <option value="">（未设置）</option>
          <option v-for="v in dataCfg.variables" :key="v.var_name" :value="v.var_name">{{ v.var_name }} {{ v.label_zh ? '（'+v.label_zh+'）' : '' }}</option>
        </select>
        <label class="flex items-center gap-2 text-sm mb-3"><input type="checkbox" v-model="dataCfg.script_only" /> 仅脚本模式（数据大/不在服务器改，改为生成脚本本地运行）</label>
        <div class="label-cap mb-1">各变量脱敏动作</div>
        <div class="border border-line rounded divide-y divide-line max-h-56 overflow-y-auto">
          <div v-for="v in dataCfg.variables" :key="v.var_name" class="flex items-center gap-2 px-3 py-1.5 text-sm">
            <span class="font-mono text-xs flex-1">{{ v.var_name }}</span>
            <select v-model="v.mask_action" class="input py-1 w-28 text-xs">
              <option value="keep">保留</option><option value="drop">删除</option>
              <option value="hash">哈希</option><option value="bucket">分桶</option>
            </select>
            <input v-if="v.mask_action==='bucket'" v-model.number="v.bucket_size" type="number" class="input py-1 w-20 text-xs" placeholder="桶宽" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-3">
          <button class="btn-ghost" @click="showDataCfg=false">取消</button>
          <button class="btn-primary" @click="saveDataCfg">保存</button>
        </div>
      </div>
    </div>

    <!-- 全部成员弹窗（检索栏在最上方）-->
    <div v-if="showMembers" class="fixed inset-0 bg-black/40 flex items-start justify-center z-50 pt-16" @click.self="showMembers=false">
      <div class="bg-white rounded-lg max-w-lg w-full m-4 max-h-[75vh] flex flex-col">
        <div class="p-4 border-b border-line">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-lg">全部成员（{{ d.members?.length || 0 }}）</h3>
            <button class="text-gray-400" @click="showMembers=false">×</button>
          </div>
          <input v-model="memberQ" class="input" placeholder="按姓名或 ID 检索成员" />
        </div>
        <div class="overflow-y-auto divide-y divide-line">
          <div v-for="m in filteredMembers" :key="m.user_id" class="flex items-center gap-2 px-4 py-2.5 text-sm">
            <router-link :to="`/users/${m.user_id}`" class="text-accent hover:underline">{{ m.name }}</router-link>
            <span class="text-gray-400 text-xs">ID {{ m.user_id }}</span>
            <span class="tag" :class="m.is_lead ? 'border-accent text-accent' : ''">{{ roleLabel(m) }}</span>
          </div>
          <p v-if="!filteredMembers.length" class="px-4 py-6 text-center text-gray-400 text-sm">没有匹配的成员。</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ds-download-fab {
  position: fixed; left: 22px; bottom: 22px; z-index: 55;
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; border-radius: 9999px;
  background: var(--accent); color: #fff; font-size: 13px;
  box-shadow: 0 6px 20px rgba(45, 74, 124, .35);
  transition: transform .15s, box-shadow .15s;
}
.ds-download-fab:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(45, 74, 124, .45); }
</style>
