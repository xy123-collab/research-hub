<script setup lang="ts">
// 研究广场 = 统一讨论系统。三栏：左热榜 / 中信息流 / 右分类筛选。
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuth } from '../stores/auth'
import api from '../api'
import Icon from '../components/Icon.vue'
import PostCard from '../components/PostCard.vue'
import PostComposer from '../components/PostComposer.vue'

const { t } = useI18n(); const auth = useAuth()
const route = useRoute(); const router = useRouter()

const posts = ref<any[]>([]); const loading = ref(false)
const hot = ref<any[]>([]); const hotRange = ref('7d')
const myGroups = ref<any[]>([]); const myDatasets = ref<any[]>([])

const TYPES = [
  { v: 'question', label: '研究问题' }, { v: 'data', label: '数据问题' },
  { v: 'method', label: '方法讨论' }, { v: 'collab', label: '合作招募' },
  { v: 'discussion', label: '自由讨论' },
]

// 筛选状态（与 URL 同步，便于分享/返回）
const f = ref<any>({ group: null, dataset: null, type: null, status: null, mine: null, sort: 'new' })
function readUrl() {
  f.value = {
    group: route.query.group ? +route.query.group : null,
    dataset: route.query.dataset ? +route.query.dataset : null,
    type: (route.query.type as string) || null,
    status: (route.query.status as string) || null,
    mine: (route.query.mine as string) || null,
    sort: (route.query.sort as string) || 'new',
  }
}
function writeUrl() {
  const q: any = {}
  if (f.value.group) q.group = f.value.group
  if (f.value.dataset) q.dataset = f.value.dataset
  if (f.value.type) q.type = f.value.type
  if (f.value.status) q.status = f.value.status
  if (f.value.mine) q.mine = f.value.mine
  if (f.value.sort !== 'new') q.sort = f.value.sort
  router.replace({ query: q })
}
const MINE = [['authored', '我的帖子'], ['liked', '我的点赞'], ['followed', '我的关注'], ['commented', '我的评论']]
function setMine(v: string) { f.value.mine = f.value.mine === v ? null : v; apply() }

const composerOpen = ref(false); const editing = ref<any>(null)
function openCompose() { editing.value = null; composerOpen.value = true }
function onEdit(post: any) { editing.value = post; composerOpen.value = true }

async function load() {
  loading.value = true
  try {
    const params: any = { sort: f.value.sort }
    if (f.value.group) params.group_id = f.value.group
    if (f.value.dataset) params.dataset_id = f.value.dataset
    if (f.value.type) params.post_type = f.value.type
    if (f.value.status) params.status = f.value.status
    if (f.value.mine) params.mine = f.value.mine
    posts.value = (await api.get('/posts', { params })).data
  } finally { loading.value = false }
}
async function loadHot() { hot.value = (await api.get('/posts/hot', { params: { range: hotRange.value } })).data }
async function loadScopes() {
  try {
    const r = (await api.get('/me/collab-scopes')).data
    myGroups.value = r.groups || []; myDatasets.value = r.datasets || []
  } catch {}
}

// 定位单条帖子（从热榜/组内动态/消息点进来的 ?post=id）
const focusPost = ref<any>(null)
async function loadFocus() {
  const id = route.query.post
  if (!id) { focusPost.value = null; return }
  try { focusPost.value = (await api.get(`/posts/${id}`)).data }
  catch { focusPost.value = null }
}
function clearFocus() { focusPost.value = null; router.replace({ query: {} }); readUrl() }

onMounted(async () => { readUrl(); await Promise.all([load(), loadHot(), loadScopes(), loadFocus()]) })
watch(hotRange, loadHot)
watch(() => route.query.post, loadFocus)

// 右栏层级：选中课题组后，数据集只显示该组下的
const datasetsForFilter = computed(() =>
  f.value.group ? myDatasets.value.filter(d => d.group_id === f.value.group) : myDatasets.value)

function setGroup(id: number | null) { f.value.group = id; f.value.dataset = null; apply() }
function setDataset(id: number | null) {
  f.value.dataset = id
  if (id) { const d = myDatasets.value.find(x => x.id === id); if (d?.group_id) f.value.group = d.group_id }
  apply()
}
function setType(v: string | null) { f.value.type = f.value.type === v ? null : v; apply() }
function setStatus(v: string | null) { f.value.status = f.value.status === v ? null : v; apply() }
function setSort(v: string) { f.value.sort = v; apply() }
function clearFilters() { f.value = { group: null, dataset: null, type: null, status: null, mine: null, sort: f.value.sort }; apply() }
function apply() { writeUrl(); load() }

const activeChips = computed(() => {
  const chips: any[] = []
  if (f.value.group) chips.push({ k: 'group', label: '课题组：' + (myGroups.value.find(g => g.id === f.value.group)?.name || f.value.group) })
  if (f.value.dataset) chips.push({ k: 'dataset', label: '数据集：' + (myDatasets.value.find(d => d.id === f.value.dataset)?.name || f.value.dataset) })
  if (f.value.type) chips.push({ k: 'type', label: TYPES.find(x => x.v === f.value.type)?.label })
  if (f.value.status) chips.push({ k: 'status', label: f.value.status === 'open' ? '仅未解决' : f.value.status })
  if (f.value.mine) chips.push({ k: 'mine', label: (MINE.find(x => x[0] === f.value.mine) || [])[1] })
  return chips
})
function removeChip(k: string) { (f.value as any)[k] = null; if (k === 'group') f.value.dataset = null; apply() }

function onSaved() { load(); loadHot() }
function onDeleted(id: number) { posts.value = posts.value.filter(p => p.id !== id); loadHot() }
</script>
<template>
  <div class="flex items-center justify-between mb-4">
    <h1 class="text-2xl">{{ t('nav.feed') }}</h1>
    <button class="btn-primary" @click="openCompose">＋发布讨论</button>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-[220px_1fr_220px] gap-5 items-start">
    <!-- 左：研究热榜 -->
    <aside class="hidden lg:block lg:sticky lg:top-4">
      <div class="card p-3">
        <div class="flex items-center justify-between mb-2">
          <span class="font-medium text-sm">🔥 研究热榜</span>
        </div>
        <div class="flex gap-1 mb-2 text-xs">
          <button v-for="r in [['24h','24小时'],['7d','7天'],['all','全部']]" :key="r[0]"
            :class="['px-2 py-0.5 rounded', hotRange===r[0] ? 'bg-accent text-white' : 'bg-paper text-gray-500']"
            @click="hotRange=r[0]">{{ r[1] }}</button>
        </div>
        <ol class="space-y-2">
          <li v-for="(h,i) in hot" :key="h.id" class="text-sm flex gap-2">
            <span :class="['font-mono w-4 shrink-0', i<3 ? 'text-accent2 font-bold' : 'text-gray-400']">{{ i+1 }}</span>
            <router-link :to="`/feed?post=${h.id}`" class="hover:text-accent line-clamp-2 leading-snug">{{ h.title }}
              <span class="block text-[11px] text-gray-400">♥{{ h.likes }} · 💬{{ h.comment_count }}</span>
            </router-link>
          </li>
        </ol>
        <p v-if="!hot.length" class="text-xs text-gray-400">暂无热门讨论。</p>
      </div>
    </aside>

    <!-- 中：信息流 -->
    <main>
      <!-- 排序 + 已选筛选 chip -->
      <div class="flex items-center gap-2 mb-3 flex-wrap">
        <div class="flex gap-1 text-sm">
          <button :class="['px-3 py-1 rounded-full', f.sort==='new' ? 'bg-accent text-white' : 'bg-paper text-gray-600']" @click="setSort('new')">最新</button>
          <button :class="['px-3 py-1 rounded-full', f.sort==='hot' ? 'bg-accent text-white' : 'bg-paper text-gray-600']" @click="setSort('hot')">最热</button>
        </div>
        <template v-for="c in activeChips" :key="c.k">
          <span class="tag flex items-center gap-1">{{ c.label }}
            <button class="text-accent2" @click="removeChip(c.k)">×</button></span>
        </template>
        <button v-if="activeChips.length" class="text-xs text-gray-400 hover:text-accent2" @click="clearFilters">清除全部</button>
      </div>

      <!-- 定位到的单条帖子（从热榜/组内动态/消息跳来）-->
      <div v-if="focusPost" class="mb-4">
        <div class="flex items-center justify-between mb-1.5 text-xs text-gray-500">
          <span>已定位到该讨论</span>
          <button class="text-accent hover:underline" @click="clearFocus">← 返回全部讨论</button>
        </div>
        <PostCard :post="focusPost" :current-user-id="auth.user?.id"
          @edit="onEdit" @deleted="() => { clearFocus() }" @changed="loadFocus" />
      </div>

      <p v-if="loading" class="text-gray-400 text-sm">加载中…</p>
      <PostCard v-for="p in posts" :key="p.id" :post="p" :current-user-id="auth.user?.id"
        @edit="onEdit" @deleted="onDeleted" @changed="load" />
      <p v-if="!loading && !posts.length" class="text-gray-400 text-sm">还没有符合条件的讨论。换个筛选，或发布第一条。</p>
    </main>

    <!-- 右：分类筛选 -->
    <aside class="hidden lg:block lg:sticky lg:top-4">
      <div class="card p-3">
        <div class="label-cap mb-1.5">按类型</div>
        <div class="flex flex-wrap gap-1 mb-3">
          <button v-for="tp in TYPES" :key="tp.v"
            :class="['text-xs px-2 py-0.5 rounded-full border', f.type===tp.v ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
            @click="setType(tp.v)">{{ tp.label }}</button>
        </div>

        <div class="label-cap mb-1.5">按课题组</div>
        <div class="space-y-0.5 mb-3">
          <button :class="['block w-full text-left text-sm px-2 py-1 rounded', !f.group ? 'bg-paper text-accent' : 'hover:bg-paper']" @click="setGroup(null)">全部课题组</button>
          <button v-for="g in myGroups" :key="g.id"
            :class="['block w-full text-left text-sm px-2 py-1 rounded truncate', f.group===g.id ? 'bg-paper text-accent' : 'hover:bg-paper']"
            @click="setGroup(g.id)">{{ g.name }}</button>
          <p v-if="!myGroups.length" class="text-xs text-gray-400 px-2">暂无课题组</p>
        </div>

        <div class="label-cap mb-1.5">按数据集<span v-if="f.group" class="text-gray-400">（该组下）</span></div>
        <div class="space-y-0.5 mb-3">
          <button :class="['block w-full text-left text-sm px-2 py-1 rounded', !f.dataset ? 'bg-paper text-accent' : 'hover:bg-paper']" @click="setDataset(null)">全部数据集</button>
          <button v-for="d in datasetsForFilter" :key="d.id"
            :class="['block w-full text-left text-sm px-2 py-1 rounded truncate', f.dataset===d.id ? 'bg-paper text-accent' : 'hover:bg-paper']"
            @click="setDataset(d.id)">{{ d.name }}</button>
          <p v-if="!datasetsForFilter.length" class="text-xs text-gray-400 px-2">暂无数据集</p>
        </div>

        <div class="label-cap mb-1.5">其他</div>
        <button :class="['text-xs px-2 py-0.5 rounded-full border', f.status==='open' ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
          @click="setStatus('open')">仅看未解决</button>
        <button :class="['text-xs px-2 py-0.5 rounded-full border ml-1', f.type==='collab' ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
          @click="setType('collab')">仅看合作招募</button>

        <div class="label-cap mt-3 mb-1.5">按我参与</div>
        <div class="flex flex-col gap-1">
          <button v-for="m in MINE" :key="m[0]"
            :class="['text-left text-sm px-2 py-1 rounded', f.mine===m[0] ? 'bg-paper text-accent' : 'hover:bg-paper text-gray-600']"
            @click="setMine(m[0])">{{ m[1] }}</button>
        </div>
      </div>
    </aside>
  </div>

  <PostComposer v-if="composerOpen" :edit="editing" @close="composerOpen=false" @saved="onSaved" />
</template>
