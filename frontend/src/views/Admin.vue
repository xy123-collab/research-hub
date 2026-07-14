<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
// 我管理的范围（可切换查看不同课题组/数据集）
const scopes = ref<any>({ groups: [], datasets: [], is_super: false })
const sel = ref<any>(null)            // {kind:'group'|'dataset'|'platform', slug}
const console_ = ref<any>(null)       // 当前所选对象的控制台数据
const mem = ref<any>(null)            // 数据集成员与权限（用于内联操作）
const err = ref('')
// 平台级
const audit = ref<any[]>([])
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
  try {
    if (kind === 'dataset') {
      console_.value = (await api.get(`/admin/datasets/${slug}/console`)).data
      mem.value = (await api.get(`/datasets/${slug}/members`)).data
    } else if (kind === 'group') {
      console_.value = (await api.get(`/admin/groups/${slug}/console`)).data
    } else if (kind === 'platform') {
      audit.value = (await api.get('/admin/audit-log', { params: { limit: 40 } })).data
      superInfo.value = (await api.get('/admin/super-admins')).data
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
