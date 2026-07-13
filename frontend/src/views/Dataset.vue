<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api'
import CharterModal from '../components/CharterModal.vue'

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
const groupsForAttach = ref<any[]>([]); const showAttach = ref(false); const attachSlug = ref('')

const tabs = [
  ['overview', 'ds.overview'], ['activity', 'ds.activity'], ['dashboard', 'ds.dashboard'],
  ['versions', 'ds.versions'], ['bugs', 'ds.bugs'], ['code', 'ds.code'],
  ['literature', 'ds.literature'], ['verify', 'ds.verify'], ['feed', 'ds.feed']
]

onMounted(async () => {
  d.value = (await api.get(`/datasets/${slug}`)).data
  vars.value = (await api.get(`/datasets/${slug}/variables`)).data
  loadTab('overview')
})

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
}

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
async function openAttach() {
  const gg = (await api.get('/groups')).data
  groupsForAttach.value = [...gg.mine, ...gg.discover]; attachSlug.value = ''; showAttach.value = true
}
async function doAttach() {
  if (!attachSlug.value) { alert('请选择课题组'); return }
  try {
    await api.post(`/datasets/${slug}/attach-request`, null, { params: { group_slug: attachSlug.value } })
    showAttach.value = false; d.value = (await api.get(`/datasets/${slug}`)).data
    alert('已提交并入申请，待课题组管理员审批')
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function doDetach() {
  if (!confirm('确认申请移出当前课题组？需课题组管理员同意')) return
  try {
    await api.post(`/datasets/${slug}/detach-request`)
    d.value = (await api.get(`/datasets/${slug}`)).data; alert('已提交移出申请')
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
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
  pub.value = { version_id: '', changelog_zh: '', fixed: [] }; pubData.value = pubCode.value = null
  showPublish.value = true
}
async function doPublish() {
  try {
    const fd = new FormData()
    fd.append('version_id', pub.value.version_id)
    fd.append('changelog_zh', pub.value.changelog_zh)
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
async function openCode(id: number) { codeModal.value = (await api.get(`/code/${id}`)).data }
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
    <div class="flex items-start justify-between">
      <div>
        <h1 class="text-2xl">{{ d.icon }} {{ d.name_zh }}
          <span v-if="d.is_sensitive" class="tag border-accent2 text-accent2">敏感</span></h1>
        <p class="text-gray-500 mt-1">{{ d.desc_zh }}</p>
        <p class="text-sm mt-2">
          {{ t('ds.founder') }}：<router-link :to="`/users/${d.founder.id}`" class="text-accent hover:underline">{{ d.founder.name }}</router-link>
          · {{ t('ds.contact') }}：{{ d.founder.contact }}
        </p>
        <p class="text-sm mt-1 text-gray-500">
          <template v-if="d.group">{{ t('ds.groupOf') }}：<router-link :to="`/groups/${d.group.slug}`" class="text-accent hover:underline">{{ d.group.name_zh }}</router-link></template>
          <span v-else class="italic">{{ t('ds.standalone') }}</span>
          <template v-if="d.is_admin && !d.pending_group_request">
            <span class="text-gray-300"> · </span>
            <button v-if="!d.group" class="text-accent hover:underline" @click="openAttach">{{ t('ds.attachToGroup') }}</button>
            <button v-else class="text-accent2 hover:underline" @click="doDetach">{{ t('ds.detachFromGroup') }}</button>
          </template>
          <span v-if="d.pending_group_request" class="text-accent2"> · {{ t('ds.requestPending') }}（{{ d.pending_group_request.kind==='attach'?'并入':'移出' }} {{ d.pending_group_request.group_name }}）</span>
        </p>
      </div>
      <div class="flex gap-2">
        <button v-if="d.is_admin" class="btn-ghost" @click="openEdit">编辑数据集</button>
        <button v-if="!d.is_member" class="btn-ghost" @click="api.post(`/datasets/${slug}/join-requests`).then(()=>alert('已申请'))">
          {{ t('ds.joinProcess') }}
        </button>
      </div>
    </div>
    <p v-if="!d.is_member" class="text-xs text-accent2 mt-2">⚠ {{ t('ds.notMemberTip') }}</p>

    <!-- 成员协作快捷条：核心协作动作一键直达 -->
    <div v-if="d.is_member" class="flex flex-wrap gap-2 mt-4">
      <button class="btn-ghost text-xs" @click="loadTab('bugs')">📝 {{ t('ds.submitBug') }}</button>
      <button class="btn-ghost text-xs" @click="loadTab('code'); showCodeAdd=true">💻 {{ t('ds.code') }}</button>
      <button class="btn-ghost text-xs" @click="loadTab('verify')">🔍 {{ t('ds.verify') }}</button>
      <button v-if="d.is_admin" class="btn-primary text-xs" @click="loadTab('versions'); openPublish()">🗂️ {{ t('ds.publishVersion') }}</button>
    </div>

    <div class="flex gap-1 border-b border-line mt-5 text-sm overflow-x-auto">
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
        <div class="card mt-4">
          <div class="label-cap">{{ t('ds.members') }}</div>
          <table class="w-full text-sm mt-2">
            <tr v-for="m in d.members" :key="m.user_id" class="border-t border-line">
              <td class="py-1"><router-link :to="`/users/${m.user_id}`" class="text-accent hover:underline">{{ m.name }}</router-link></td>
              <td><span class="tag">{{ m.ds_role }}</span></td>
              <td class="text-gray-400 text-xs">{{ m.joined_at?.slice(0,10) }}</td>
              <td class="text-right"><button v-if="d.is_admin && m.ds_role!=='founder'" class="text-xs text-accent2" @click="removeMember(m.user_id)">移除</button></td>
            </tr>
          </table>
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
          <input v-model="aiPrompt" class="input mt-2" placeholder="用自然语言描述分析需求，如：统计各变量分布" />
          <div class="flex gap-2 mt-2">
            <button class="btn-ghost" @click="aiGen">AI 生成代码</button>
            <button class="btn-primary" @click="aiRun" :disabled="!aiCode">在沙箱运行</button>
          </div>
          <textarea v-model="aiCode" class="input mt-2 font-mono text-xs" rows="4" placeholder="生成/手写的 pandas 代码（result=...）"></textarea>
          <pre v-if="aiResult" class="mt-2">{{ JSON.stringify(aiResult, null, 2) }}</pre>
        </div>
      </div>

      <!-- versions -->
      <div v-else-if="tab==='versions'">
        <div v-if="d.is_admin" class="mb-3"><button class="btn-primary" @click="openPublish">{{ t('ds.publishVersion') }}</button></div>
        <div v-for="v in versions" :key="v.id" class="card mb-3 flex items-center justify-between">
          <div>
            <span class="font-mono">{{ v.version_id }}</span>
            <span v-if="v.is_current" class="tag ml-2">当前</span>
            <span v-if="v.based_on" class="text-xs text-gray-400 ml-2">基于 {{ v.based_on }}</span>
            <p class="text-sm text-gray-500 mt-1">{{ v.changelog_zh }}</p>
          </div>
          <div class="flex gap-2">
            <button class="btn-ghost text-xs" @click="download(v,'codebook')">Codebook</button>
            <button class="btn-ghost text-xs" @click="download(v,'data')">.dta</button>
          </div>
        </div>
        <p v-if="!versions.length" class="text-gray-400 text-sm">暂无版本。</p>
      </div>

      <!-- bugs -->
      <div v-else-if="tab==='bugs'">
        <div v-if="d.is_member" class="card mb-4">
          <div class="label-cap mb-2">{{ t('ds.submitBug') }}</div>
          <div class="grid grid-cols-2 gap-2">
            <input v-model="bugForm.officer_id" class="input" placeholder="officerID" />
            <select v-model="bugForm.variable_id" class="input">
              <option :value="null">选择变量</option>
              <option v-for="v in vars" :key="v.id" :value="v.id">{{ v.var_name }}</option>
            </select>
            <input v-model="bugForm.current_value" class="input" placeholder="当前值" />
            <input v-model="bugForm.suggested_value" class="input" placeholder="建议值" />
          </div>
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

    <!-- 申请并入课题组 -->
    <div v-if="showAttach" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showAttach=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-1">{{ t('ds.attachToGroup') }}</h3>
        <p class="text-xs text-gray-400 mb-3">并入需所选课题组的管理员同意；并入后如需移出，同样需该组管理员同意。</p>
        <select v-model="attachSlug" class="input mb-3">
          <option value="">选择课题组…</option>
          <option v-for="gg in groupsForAttach" :key="gg.slug" :value="gg.slug">{{ gg.name_zh }}</option>
        </select>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showAttach=false">{{ t('common.cancel') }}</button>
          <button class="btn-primary" @click="doAttach">{{ t('common.submit') }}</button>
        </div>
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
        <p class="text-sm mt-1">{{ bugModal.description_zh }}（{{ bugModal.current_value }} → {{ bugModal.suggested_value }}）</p>
        <p v-if="bugModal.fixed_in_version" class="text-xs text-accent mt-1">已在版本 {{ bugModal.fixed_in_version }} 修复</p>
        <div v-if="bugModal.attachments.length" class="mt-2">
          <div class="label-cap">证据附件</div>
          <a v-for="a in bugModal.attachments" :key="a.id" :href="`/api/bug-attachments/${a.id}/download`" target="_blank" class="text-accent text-xs block hover:underline">📎 {{ a.file_name }}</a>
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
        <p class="text-sm text-gray-500 mt-1">{{ codeModal.title_zh }} · {{ codeModal.desc_zh }}</p>
        <pre class="mt-2">{{ codeModal.source_code }}</pre>
        <button v-if="d.is_member" class="btn-ghost text-xs mt-2" @click="genWriteup(codeModal.id)">一键生成数据处理说明（AI）</button>
      </div>
    </div>

    <!-- 发布版本 -->
    <div v-if="showPublish" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showPublish=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4 max-h-[85vh] overflow-y-auto">
        <h3 class="text-lg mb-3">发布新版本（旧版本保留、不可覆盖）</h3>
        <input v-model="pub.version_id" class="input mb-2 font-mono" placeholder="版本号，如 v1.1.0 / v1.0.1-hotfix" />
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
  </div>
</template>
