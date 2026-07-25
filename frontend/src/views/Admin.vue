<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { downloadFile } from '../utils/download'

const router = useRouter()
// 我管理的范围（可切换查看不同课题组/数据集）
const scopes = ref<any>({ groups: [], datasets: [], is_super: false })
const sel = ref<any>(null)            // {kind:'group'|'dataset'|'platform', slug}
const console_ = ref<any>(null)       // 当前所选对象的控制台数据
const mem = ref<any>(null)            // 数据集成员与权限（用于内联操作）
const err = ref('')
// 平台级
const audit = ref<any[]>([])
const analytics = ref<any>(null)
const tickets = ref<any[]>([])
const ticketFilter = ref('')
const analyticsModule = ref('all')
const analyticsPeriod = ref<'week'|'month'>('month')
const scopePeriod = ref<'week'|'month'>('month')
const scopeActivityGroup = ref('all')
const downloadCategory = ref('all')
const downloadPeriod = ref<'all'|'month'|'week'>('all')
const superInfo = ref<any>({ admins: [], primary_uid: null, i_am_primary: false })
// 管理员检索（按名称或 ID，检索出的结果显示名称供确认）
const adminQ = ref(''); const adminResults = ref<any[]>([]); const adminPick = ref<any>(null)

onMounted(async () => {
  try { scopes.value = (await api.get('/admin/my-scopes')).data } catch (e: any) { err.value = e.response?.data?.detail }
  // 默认选中第一个可管理对象；否则平台
  if (scopes.value.datasets.length) selectScope('dataset', scopes.value.datasets[0].slug)
  else if (scopes.value.groups.length) selectScope('group', scopes.value.groups[0].slug)
  else if (scopes.value.is_super) selectScope('platform', '')
})

async function selectScope(kind: string, slug: string) {
  sel.value = { kind, slug }; console_.value = null; mem.value = null; err.value = ''
  scopeActivityGroup.value = 'all'; downloadCategory.value = 'all'; downloadPeriod.value = 'all'
  try {
    if (kind === 'dataset') {
      console_.value = (await api.get(`/admin/datasets/${slug}/console`)).data
      mem.value = (await api.get(`/datasets/${slug}/members`)).data
    } else if (kind === 'group') {
      console_.value = (await api.get(`/admin/groups/${slug}/console`)).data
    } else if (kind === 'platform') {
      const [ar, sr, tr, an] = await Promise.all([
        api.get('/admin/audit-log', { params: { limit: 40 } }),
        api.get('/admin/super-admins'), api.get('/admin/feedback'),
        api.get('/admin/platform-analytics')
      ])
      audit.value = ar.data; superInfo.value = sr.data; tickets.value = tr.data; analytics.value = an.data
    }
  } catch (e: any) { err.value = e.response?.data?.detail || '加载失败' }
}

const a = computed(() => console_.value?.activity || {})
const pend = computed(() => console_.value?.pending || {})

// 数据集内联审批/授权（复用后端接口）
async function reloadDsMem() { mem.value = (await api.get(`/datasets/${sel.value.slug}/members`)).data;
  console_.value = (await api.get(`/admin/datasets/${sel.value.slug}/console`)).data }
async function decideJoin(id: number, approve: boolean) {
  await api.post(`/join-requests/${id}/decide`, null, { params: { approve } }); reloadDsMem()
}
async function decideDownload(id: number, approve: boolean) {
  let valid_to = ''
  if (approve) valid_to = prompt('可选：授权有效期（YYYY-MM-DD，留空长期有效）', '') || ''
  await api.post(`/download-requests/${id}/decide`, null, { params: { approve, valid_to } }); reloadDsMem()
}

// 按名称或 ID 检索用户（结果显示名称供确认）
async function searchAdmin() {
  const q = adminQ.value.trim()
  adminResults.value = (await api.get('/users/search', { params: { q } })).data
  adminPick.value = null
}
function pickAdmin(u: any) { adminPick.value = u }
async function addSuper() {
  if (!adminPick.value) { alert('请先检索并选择一个用户'); return }
  if (!confirm(`确认添加「${adminPick.value.display_name}」（ID ${adminPick.value.id}）为总管理员？`)) return
  try {
    await api.post('/admin/super-admins', null, { params: { uid: adminPick.value.id } })
    adminQ.value = ''; adminResults.value = []; adminPick.value = null; selectScope('platform', '')
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function transferPrimary() {
  if (!adminPick.value) { alert('请先检索并选择一个用户'); return }
  if (!confirm(`确认把「平台总管理员」头衔交接给「${adminPick.value.display_name}」（ID ${adminPick.value.id}）？你将降为其他管理员。`)) return
  try {
    await api.post('/admin/super-admins/transfer', null, { params: { uid: adminPick.value.id } })
    adminQ.value = ''; adminResults.value = []; adminPick.value = null; selectScope('platform', '')
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function revokeSuper(s: any) {
  if (!confirm(`确认移除「${s.display_name}」的总管理员身份？`)) return
  try { await api.delete(`/admin/super-admins/${s.id}`); selectScope('platform', '') }
  catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
const roleTag = (r: string) => r === 'lead' ? '总管理员' : '管理员'
const platformFeatures = computed(() => {
  const modules = analytics.value?.modules || []
  if (analyticsModule.value === 'all') {
    return modules.flatMap((m:any) => m.features.map((f:any) => ({...f, module:m.name})))
      .sort((x:any,y:any) => y[analyticsPeriod.value] - x[analyticsPeriod.value])
  }
  const m = modules.find((x:any) => x.key === analyticsModule.value)
  return (m?.features || []).map((f:any) => ({...f, module:m.name}))
})
const maxFeature = computed(() => Math.max(1, ...platformFeatures.value.map((x:any) => x[analyticsPeriod.value])))
const scopeGroups = computed(() => Array.from(new Set((console_.value?.feature_activity || []).map((x:any)=>x.group))))
const scopeFeatures = computed(() => (console_.value?.feature_activity || [])
  .filter((x:any) => scopeActivityGroup.value === 'all' || x.group === scopeActivityGroup.value))
const maxScopeFeature = computed(() => Math.max(1, ...scopeFeatures.value.map((x:any)=>x[scopePeriod.value])))
const downloadCategories = computed(() => Array.from(new Set((console_.value?.download_history || []).map((x:any)=>x.category))))
const shownDownloads = computed(() => (console_.value?.download_history || [])
  .filter((x:any) => downloadCategory.value === 'all' || x.category === downloadCategory.value)
  .filter((x:any) => {
    if (downloadPeriod.value === 'all') return true
    const days = downloadPeriod.value === 'week' ? 7 : 30
    return new Date(x.downloaded_at).getTime() >= Date.now() - days*86400000
  }))
const dailyMax = computed(() => Math.max(1, ...(analytics.value?.daily_active || []).map((x:any)=>x.active_users)))
const yTicks = computed(() => [dailyMax.value, Math.ceil(dailyMax.value/2), 0])
const shownTickets = computed(() => ticketFilter.value
  ? tickets.value.filter((x:any) => x.status === ticketFilter.value) : tickets.value)
const statusLabel: any = { pending:'待受理', processing:'处理中', waiting_user:'等待用户补充',
  resolved:'已解决', closed:'已关闭', rejected:'不予处理' }
async function updateTicket(row:any, status:string) {
  const reply = prompt('给提交人的处理说明（可留空）', row.admin_reply || '')
  if (reply === null) return
  await api.patch(`/admin/feedback/${row.id}`, { status, admin_reply: reply })
  const tr = await api.get('/admin/feedback'); tickets.value = tr.data
  analytics.value = (await api.get('/admin/platform-analytics')).data
}
function exportDownloads() {
  downloadFile(`/admin/${sel.value.kind}/${sel.value.slug}/downloads.xlsx`,
    `${sel.value.slug}_download_history.xlsx`)
}
</script>

<template>
  <h1 class="text-2xl mb-1">管理后台</h1>
  <p class="text-xs text-gray-500 mb-4">按你管理的课题组 / 数据集切换查看：贡献度、近30天活跃度、最新消息与权限审批。总管理员只见平台系统与动作元数据审计，看不到内容明细。</p>

  <p v-if="err && !sel" class="text-accent2 text-sm">{{ err }}</p>

  <!-- 范围选择器 -->
  <div class="flex flex-wrap gap-2 mb-5">
    <template v-if="scopes.datasets.length">
      <button v-for="d in scopes.datasets" :key="'d'+d.slug" @click="selectScope('dataset', d.slug)"
        :class="['px-3 py-1.5 rounded text-xs border transition', sel?.kind==='dataset'&&sel?.slug===d.slug ? 'bg-accent text-white border-accent' : 'border-line bg-white hover:bg-paper']">
        数据集 · {{ d.name_zh }} <span class="opacity-70">（{{ roleTag(d.role) }}）</span>
      </button>
    </template>
    <template v-if="scopes.groups.length">
      <button v-for="g in scopes.groups" :key="'g'+g.slug" @click="selectScope('group', g.slug)"
        :class="['px-3 py-1.5 rounded text-xs border transition', sel?.kind==='group'&&sel?.slug===g.slug ? 'bg-accent text-white border-accent' : 'border-line bg-white hover:bg-paper']">
        课题组 · {{ g.name_zh }} <span class="opacity-70">（{{ roleTag(g.role) }}）</span>
      </button>
    </template>
    <button v-if="scopes.is_super" @click="selectScope('platform', '')"
      :class="['px-3 py-1.5 rounded text-xs border transition', sel?.kind==='platform' ? 'bg-accent text-white border-accent' : 'border-line bg-white hover:bg-paper']">
      平台系统（总管理员）
    </button>
  </div>

  <p v-if="!scopes.datasets.length && !scopes.groups.length && !scopes.is_super" class="text-gray-400 text-sm">
    你目前不是任何课题组或数据集的管理员。成为管理员后，这里会显示对应的贡献度、活跃度与审批。
  </p>

  <!-- ========== 数据集 / 课题组控制台 ========== -->
  <div v-if="console_ && sel?.kind!=='platform'">
    <!-- 活跃度指标卡 -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
      <template v-if="sel.kind==='dataset'">
        <div class="card"><div class="label-cap">近30天发版</div><p class="text-2xl mt-1">{{ a.versions_30d ?? 0 }}</p></div>
        <div class="card"><div class="label-cap">近30天下载</div><p class="text-2xl mt-1">{{ a.downloads_30d ?? 0 }}</p></div>
        <div class="card"><div class="label-cap">勘误（待处理/总）</div><p class="text-2xl mt-1">{{ a.corrections_pending ?? 0 }}<span class="text-gray-400 text-base">/{{ a.corrections_total ?? 0 }}</span></p></div>
        <div class="card"><div class="label-cap">代码 / 评论</div><p class="text-2xl mt-1">{{ a.code_total ?? 0 }}<span class="text-gray-400 text-base"> / {{ a.comments_total ?? 0 }}</span></p></div>
      </template>
      <template v-else>
        <div class="card"><div class="label-cap">数据集 / 成员</div><p class="text-2xl mt-1">{{ a.datasets ?? 0 }} / {{ a.members ?? 0 }}</p></div>
        <div class="card"><div class="label-cap">近30天发版</div><p class="text-2xl mt-1">{{ a.versions_30d ?? 0 }}</p></div>
        <div class="card"><div class="label-cap">勘误 / 代码</div><p class="text-2xl mt-1">{{ a.corrections_total ?? 0 }} / {{ a.code_total ?? 0 }}</p></div>
        <div class="card"><div class="label-cap">发帖 / 评论</div><p class="text-2xl mt-1">{{ a.posts_total ?? 0 }} / {{ a.comments_total ?? 0 }}</p></div>
      </template>
    </div>

    <section class="card mb-5">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div><h2 class="text-base">{{ sel.kind==='dataset' ? '数据集功能活跃度' : '研究项目功能活跃度' }}</h2>
          <p class="text-xs text-gray-400 mt-1">基于真实发布、讨论和下载记录统计。</p></div>
        <div class="flex gap-1 whitespace-nowrap">
          <button v-for="[k,l] in [['week','近7天'],['month','近30天']]" :key="k"
            :class="['px-3 py-1.5 rounded-full text-xs border',scopePeriod===k?'bg-accent text-white border-accent':'border-line']"
            @click="scopePeriod=k as any">{{ l }}</button>
        </div>
      </div>
      <div class="flex flex-wrap gap-2 mb-4">
        <button :class="['px-3 py-1 rounded-full text-xs border',scopeActivityGroup==='all'?'bg-paper border-accent text-accent':'border-line']" @click="scopeActivityGroup='all'">全部</button>
        <button v-for="g in scopeGroups" :key="String(g)"
          :class="['px-3 py-1 rounded-full text-xs border',scopeActivityGroup===g?'bg-paper border-accent text-accent':'border-line']"
          @click="scopeActivityGroup=String(g)">{{ g }}</button>
      </div>
      <div v-for="f in scopeFeatures" :key="f.group+f.name" class="grid grid-cols-[minmax(150px,240px)_1fr_52px] items-center gap-3 mb-3 text-xs">
        <span class="truncate" :title="f.name"><span class="text-gray-400">{{ f.group }} · </span>{{ f.name }}</span>
        <div class="h-4 rounded bg-gray-100 overflow-hidden"><div class="h-full bg-accent rounded" :style="{width:(f[scopePeriod]/maxScopeFeature*100)+'%'}"></div></div>
        <span class="text-right font-mono whitespace-nowrap">{{ f[scopePeriod] }} 次</span>
      </div>
    </section>

    <section class="mb-6">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-2">
        <div><h2 class="text-base">文件下载历史</h2><p class="text-xs text-gray-400 mt-1">默认显示约5条高度，可在方框内滚动查看全部真实记录。</p></div>
        <div class="flex flex-wrap gap-2">
          <select v-model="downloadCategory" class="input w-40 text-xs whitespace-nowrap">
            <option value="all">全部类别</option><option v-for="c in downloadCategories" :key="String(c)" :value="c">{{ c }}</option>
          </select>
          <select v-model="downloadPeriod" class="input w-32 text-xs whitespace-nowrap">
            <option value="all">不限日期</option><option value="month">近30天</option><option value="week">近7天</option>
          </select>
          <button class="btn-ghost text-xs whitespace-nowrap" @click="exportDownloads">导出全部 Excel</button>
        </div>
      </div>
      <div class="card p-0 overflow-x-auto">
        <div class="max-h-[270px] overflow-y-auto">
        <table class="w-full min-w-[760px] text-xs">
          <thead class="sticky top-0 bg-white z-10"><tr class="text-left text-gray-400 whitespace-nowrap"><th class="px-4 py-2">类别</th><th>下载用户</th><th>下载内容</th><th>所在位置</th><th class="pr-4">时间</th></tr></thead>
          <tbody><tr v-for="x in shownDownloads" :key="x.id" class="border-t border-line">
            <td class="px-4 py-2 whitespace-nowrap"><span class="tag whitespace-nowrap">{{ x.category }}</span></td>
            <td class="py-2 whitespace-nowrap">{{ x.user_name }} <span class="text-gray-400">ID {{ x.user_id }}</span></td>
            <td class="py-2">{{ x.file_name }}<span v-if="x.detail" class="block text-gray-400">{{ x.detail }}</span></td>
            <td class="py-2">{{ x.location || '—' }}</td><td class="py-2 pr-4 whitespace-nowrap text-gray-400">{{ x.downloaded_at?.slice(0,19) }}</td>
          </tr><tr v-if="!shownDownloads.length"><td colspan="5" class="py-4 text-center text-gray-400">暂无该类别的下载记录。</td></tr></tbody>
        </table>
        </div>
      </div>
    </section>

    <div class="grid md:grid-cols-2 gap-5">
      <!-- 贡献度 -->
      <section>
        <h2 class="text-base text-gray-500 font-normal mb-2 pb-2 border-b border-line">成员贡献度</h2>
        <div class="card">
          <table class="w-full text-sm">
            <tr v-for="r in console_.contributions" :key="r.user_id" class="border-t border-line first:border-0">
              <td class="py-1"><router-link :to="`/users/${r.user_id}`" class="text-accent hover:underline">{{ r.name }}</router-link><span class="text-gray-400 text-xs ml-1">ID {{ r.user_id }}</span></td>
              <td class="text-right font-mono">{{ r.score }}</td>
            </tr>
            <tr v-if="!console_.contributions.length"><td class="text-gray-400 py-1">暂无贡献记录。</td></tr>
          </table>
        </div>
      </section>

      <!-- 最新消息 -->
      <section>
        <h2 class="text-base text-gray-500 font-normal mb-2 pb-2 border-b border-line">最新消息</h2>
        <div class="rounded-lg border border-line bg-white divide-y divide-line">
          <div v-for="(e,i) in console_.recent" :key="i" class="px-4 py-2.5 text-sm flex items-center gap-2">
            <span class="dot" :style="{ background: e.type==='version' ? '#2d4a7c' : '#7c2d3a' }"></span>
            <span class="flex-1 truncate">{{ e.text }}</span>
            <span class="text-gray-400 text-xs">{{ e.at }}</span>
          </div>
          <p v-if="!console_.recent.length" class="px-4 py-3 text-gray-400 text-sm">暂无更新。</p>
        </div>
      </section>
    </div>

    <!-- 数据集：内联权限审批与操作 -->
    <section v-if="sel.kind==='dataset' && mem" class="mt-6">
      <div class="flex items-center justify-between mb-2 pb-2 border-b border-line">
        <h2 class="text-base text-gray-500 font-normal">成员与权限审批</h2>
        <button class="btn-ghost text-xs" @click="router.push(`/datasets/${sel.slug}?tab=access`)">前往完整管理页 →</button>
      </div>
      <div class="card mb-3" v-if="mem.requests?.length">
        <div class="label-cap mb-2">加入申请（{{ mem.requests.length }}）</div>
        <div v-for="r in mem.requests" :key="r.id" class="flex items-center gap-2 text-sm border-t border-line py-2 first:border-0">
          <router-link :to="`/users/${r.user_id}`" class="text-accent hover:underline">{{ r.name }}</router-link>
          <span class="text-gray-400 truncate">{{ r.message }}</span>
          <div class="ml-auto flex gap-2">
            <button class="btn-primary text-xs" @click="decideJoin(r.id, true)">通过</button>
            <button class="btn-ghost text-xs" @click="decideJoin(r.id, false)">拒绝</button>
          </div>
        </div>
      </div>
      <div class="card mb-3" v-if="mem.download_requests?.length">
        <div class="label-cap mb-2">下载申请（{{ mem.download_requests.length }}）</div>
        <div v-for="r in mem.download_requests" :key="r.id" class="text-sm border-t border-line py-2 first:border-0">
          <div class="flex items-center gap-2">
            <router-link :to="`/users/${r.user_id}`" class="text-accent hover:underline">{{ r.name }}</router-link>
            <span class="text-gray-400">版本 {{ r.scope_version || '当前' }}</span>
            <div class="ml-auto flex gap-2">
              <button class="btn-primary text-xs" @click="decideDownload(r.id, true)">批准</button>
              <button class="btn-ghost text-xs" @click="decideDownload(r.id, false)">拒绝</button>
            </div>
          </div>
          <p class="text-gray-500 mt-1">用途：{{ r.purpose }}</p>
        </div>
      </div>
      <p v-if="!mem.requests?.length && !mem.download_requests?.length" class="text-gray-400 text-sm">暂无待审批的加入 / 下载申请。授权设置请前往完整管理页。</p>
    </section>

    <!-- 课题组：跳转到组页处理申请 -->
    <section v-else-if="sel.kind==='group'" class="mt-6">
      <div class="flex items-center gap-3">
        <span v-if="pend.join_requests" class="tag border-accent2 text-accent2">待处理加入申请 {{ pend.join_requests }}</span>
        <button class="btn-ghost text-xs" @click="router.push(`/groups/${sel.slug}`)">前往课题组管理 →</button>
      </div>
    </section>
  </div>

  <!-- ========== 平台系统（总管理员）========== -->
  <div v-if="sel?.kind==='platform'">
    <section v-if="analytics" class="mb-6">
      <h2 class="text-lg mb-2">平台运营总览</h2>
      <p class="text-xs text-gray-500 mb-3">以下是数据库中的真实记录，不是模拟数据。功能活跃度来自审计日志，未埋点的单纯页面浏览不会被计入；不读取私有研究内容。</p>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-5">
        <div v-for="[k,l] in [['users','用户'],['projects','研究项目'],['datasets','数据集'],['wau','周活用户'],['mau','月活用户'],['open_feedback','待处理反馈']]"
          :key="k" class="card"><div class="label-cap">{{ l }}</div><p class="text-2xl mt-1">{{ analytics.overview[k] }}</p></div>
      </div>
      <div class="flex flex-col gap-5">
        <div class="card order-2">
          <div class="flex flex-wrap justify-between items-start gap-3 mb-3">
            <div><h3>功能使用活跃度</h3><p class="text-xs text-gray-400 mt-1">选择“全部”混排所有子功能，或按大模块查看内部子功能。</p></div>
            <div class="flex gap-1 whitespace-nowrap">
              <button v-for="[k,l] in [['week','近7天'],['month','近30天']]" :key="k"
                :class="['px-3 py-1.5 rounded-full text-xs border',analyticsPeriod===k?'bg-accent text-white border-accent':'border-line']"
                @click="analyticsPeriod=k as any">{{ l }}</button>
            </div>
          </div>
          <div class="flex flex-wrap gap-2 mb-4">
            <button :class="['px-3 py-1 rounded-full text-xs border',analyticsModule==='all'?'bg-paper border-accent text-accent':'border-line']" @click="analyticsModule='all'">全部子功能</button>
            <button v-for="m in analytics.modules" :key="m.key"
              :class="['px-3 py-1 rounded-full text-xs border',analyticsModule===m.key?'bg-paper border-accent text-accent':'border-line']"
              @click="analyticsModule=m.key">{{ m.name }} <span class="font-mono ml-1">{{ m[analyticsPeriod] }}</span></button>
          </div>
          <div v-for="f in platformFeatures" :key="f.module+f.name" class="grid grid-cols-[minmax(240px,330px)_1fr_52px] items-center gap-3 mb-3 text-xs">
            <span class="leading-5" :title="`${f.module} · ${f.name}`"><span class="text-gray-400">{{ f.module }} · </span>{{ f.name }}</span>
            <div class="h-4 rounded bg-gray-100 overflow-hidden"><div class="h-full bg-accent rounded" :style="{width: (f[analyticsPeriod]/maxFeature*100)+'%'}"></div></div>
            <span class="text-right font-mono whitespace-nowrap">{{ f[analyticsPeriod] }} 次</span>
          </div>
        </div>
        <div class="card order-1">
          <h3 class="mb-3">近30日每日活跃用户</h3>
          <div class="grid grid-cols-[34px_1fr] grid-rows-[150px_26px] text-[10px] text-gray-400">
            <div class="relative border-r border-line">
              <span v-for="(tick,i) in yTicks" :key="tick+i" class="absolute right-2 -translate-y-1/2" :style="{top:(i*50)+'%'}">{{ tick }}</span>
            </div>
            <div class="relative flex items-end gap-1 border-b border-line">
              <div v-for="tick in yTicks" :key="'line'+tick" class="absolute left-0 right-0 border-t border-dashed border-gray-100" :style="{bottom:(tick/dailyMax*100)+'%'}"></div>
              <div v-for="d in analytics.daily_active" :key="d.date" class="relative flex-1 bg-accent/70 min-h-[2px] rounded-t"
                :style="{height: Math.max(2, d.active_users/dailyMax*100)+'%'}" :title="`${d.date}：${d.active_users} 人`"></div>
            </div>
            <div class="text-right pr-2 pt-1">人数</div>
            <div class="flex justify-between pt-1"><span v-for="i in [0,5,11,17,23,29]" :key="i">{{ analytics.daily_active[i]?.date }}</span></div>
          </div>
          <p class="text-xs text-gray-400 mt-2 whitespace-nowrap">横轴：日期　纵轴：活跃用户数</p>
          <p class="text-xs text-gray-400 mt-1 whitespace-nowrap">近7天动作 {{ analytics.audit_actions_7d }} · 近30天动作 {{ analytics.audit_actions_30d }}</p>
        </div>
      </div>
    </section>

    <section class="mb-6">
      <div class="flex items-center justify-between mb-2">
        <h2 class="text-lg whitespace-nowrap">反馈与问题 <span v-if="analytics?.overview.open_feedback" class="tag text-accent2 ml-1 whitespace-nowrap">{{ analytics.overview.open_feedback }} 待处理</span></h2>
        <select v-model="ticketFilter" class="input w-36 text-xs"><option value="">全部状态</option>
          <option v-for="(label,key) in statusLabel" :key="key" :value="key">{{ label }}</option></select>
      </div>
      <div class="card overflow-x-auto">
        <table class="w-full text-xs min-w-[760px]">
          <thead><tr class="text-left text-gray-400"><th>工单</th><th>类型 / 标题</th><th>提交人</th><th>影响</th><th>状态</th><th>提交时间</th><th>处理</th></tr></thead>
          <tbody><tr v-for="x in shownTickets" :key="x.id" class="border-t border-line align-top">
            <td class="py-2">#{{ x.id }}</td><td class="py-2 max-w-xs"><span class="tag">{{ x.category }}</span><p class="mt-1">{{ x.title }}</p><p class="text-gray-400 truncate" :title="x.description">{{ x.description }}</p></td>
            <td class="py-2">{{ x.submitter?.name || '—' }}</td><td class="py-2">{{ x.impact }}</td>
            <td class="py-2">{{ statusLabel[x.status] || x.status }}</td><td class="py-2 text-gray-400">{{ x.created_at?.slice(0,16) }}</td>
            <td class="py-2"><select class="input text-xs w-28" :value="x.status" @change="updateTicket(x, ($event.target as HTMLSelectElement).value)">
              <option v-for="(label,key) in statusLabel" :key="key" :value="key">{{ label }}</option></select></td>
          </tr><tr v-if="!shownTickets.length"><td colspan="7" class="py-4 text-center text-gray-400">暂无反馈工单。</td></tr></tbody>
        </table>
      </div>
    </section>

    <section class="mb-6">
      <h2 class="text-lg mb-2">平台管理员</h2>
      <div class="card text-sm">
        <!-- 现有管理员：区分总管理员 / 其他 -->
        <div class="space-y-1.5 mb-4">
          <div v-for="s in superInfo.admins" :key="s.id" class="flex items-center gap-2">
            <span class="tag" :class="s.is_primary ? 'border-accent text-accent' : ''">
              {{ s.is_primary ? '平台总管理员' : '其他管理员' }}
            </span>
            <span>{{ s.display_name }} <span class="text-gray-400 text-xs">ID {{ s.id }} · {{ s.username }}</span></span>
            <button v-if="superInfo.i_am_primary && !s.is_primary" class="text-xs text-accent2 ml-auto"
              @click="revokeSuper(s)">移除</button>
          </div>
          <p v-if="!superInfo.admins.length" class="text-gray-400">暂无管理员。</p>
        </div>

        <!-- 检索用户（按名称或 ID）-->
        <div class="label-cap mb-1">添加 / 交接（按名称或 ID 检索）</div>
        <div class="flex items-center gap-2">
          <input v-model="adminQ" class="input w-56" placeholder="输入姓名或用户 ID" @keyup.enter="searchAdmin" />
          <button class="btn-ghost text-sm" @click="searchAdmin">检索</button>
        </div>
        <div v-if="adminResults.length" class="border border-line rounded mt-2 max-h-40 overflow-y-auto">
          <button v-for="u in adminResults" :key="u.id"
            class="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-paper"
            :class="adminPick && adminPick.id===u.id ? 'bg-paper' : ''" @click="pickAdmin(u)">
            <span>{{ u.display_name }} <span class="text-gray-400 text-xs">ID {{ u.id }} · {{ u.username }}</span></span>
            <span v-if="adminPick && adminPick.id===u.id" class="text-accent text-xs">已选 ✓</span>
          </button>
        </div>
        <div v-if="adminPick" class="mt-2 text-sm">
          已选择：<b>{{ adminPick.display_name }}</b>（ID {{ adminPick.id }}）
        </div>
        <div class="flex items-center gap-2 mt-2">
          <button class="btn-primary text-sm" :disabled="!adminPick" @click="addSuper">添加为管理员</button>
          <button v-if="superInfo.i_am_primary" class="btn-ghost text-sm" :disabled="!adminPick" @click="transferPrimary">
            交接平台总管理员
          </button>
        </div>
        <p class="text-xs text-gray-400 mt-2">
          只有「平台总管理员」可以交接头衔或移除其他管理员；管理员只负责平台运行，不接触课题组/数据集内容。
        </p>
      </div>
    </section>
    <section v-if="audit.length">
      <h2 class="text-lg mb-2">全站审计日志（动作元数据）</h2>
      <div class="card">
        <table class="w-full text-xs">
          <tr v-for="l in audit" :key="l.id" class="border-t border-line first:border-0">
            <td class="py-1">#{{ l.user_id }}</td><td><span class="tag">{{ l.action }}</span></td>
            <td>{{ l.object_type }} {{ l.object_id }}</td><td class="text-gray-400">{{ l.created_at?.slice(0,19) }}</td>
          </tr>
        </table>
      </div>
    </section>
  </div>
</template>
