<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api'

const { t } = useI18n(); const router = useRouter()
const mineDs = ref<any[]>([]); const allDs = ref<any[]>([])
const q = ref(''); const groupFilter = ref('')
const showDs = ref(false); const showGroup = ref(false)
const dsForm = ref({ slug: '', name_zh: '', desc_zh: '', founder_contact: '', is_sensitive: false })
const gForm = ref({ slug: '', name_zh: '', desc_zh: '' })

onMounted(load)
async function load() {
  const [mine, wall] = await Promise.all([api.get('/datasets/mine'), api.get('/datasets')])
  mineDs.value = mine.data; allDs.value = wall.data
}

const mineIds = computed(() => new Set(mineDs.value.map((d: any) => d.id)))
const groupOptions = computed(() => {
  const m = new Map<string, string>()
  allDs.value.forEach((d: any) => { if (d.group_slug) m.set(d.group_slug, d.group_name) })
  return [...m.entries()].map(([slug, name]) => ({ slug, name }))
})
function matchDs(d: any) {
  const kw = q.value.trim().toLowerCase()
  const okKw = !kw || `${d.name_zh}${d.desc_zh || ''}${d.group_name || ''}`.toLowerCase().includes(kw)
  const okGroup = !groupFilter.value || d.group_slug === groupFilter.value
  return okKw && okGroup
}
const mineShown = computed(() => mineDs.value.filter(matchDs))
const discoverDs = computed(() => allDs.value.filter((d: any) => !mineIds.value.has(d.id) && matchDs(d)))
const isEmpty = computed(() => !mineDs.value.length)

// 近期更新：把我的数据集的 recent 事件摊平、按日期倒序
const recentFeed = computed(() => {
  const rows: any[] = []
  mineDs.value.forEach((d: any) => (d.recent || []).forEach((e: any) =>
    rows.push({ ...e, ds_name: d.name_zh, ds_slug: d.slug, ds_icon: d.icon })))
  return rows.sort((a, b) => (b.at || '').localeCompare(a.at || '')).slice(0, 6)
})

async function createDs() {
  if (!dsForm.value.slug || !dsForm.value.name_zh || !dsForm.value.founder_contact) {
    alert('数据集标识、名称、发起人联系方式为必填'); return
  }
  try {
    const r = await api.post('/datasets', dsForm.value)
    showDs.value = false
    router.push(`/datasets/${r.data.slug}`)
  } catch (e: any) { alert(e.response?.data?.detail || '创建失败') }
}
async function createGroup() {
  if (!gForm.value.slug || !gForm.value.name_zh) { alert('请填写标识与名称'); return }
  try {
    await api.post('/groups', gForm.value); showGroup.value = false
    gForm.value = { slug: '', name_zh: '', desc_zh: '' }; router.push('/groups')
  } catch (e: any) { alert(e.response?.data?.detail || '创建失败') }
}
const evColor = (t: string) => t === 'version' ? '#2d4a7c' : '#7c2d3a'
</script>

<template>
  <!-- 价值 hero + 协作能力（极简线性图标） -->
  <section class="rounded-xl border border-line bg-white px-7 py-7 mb-6">
    <p class="eyebrow">{{ t('home.tagline') }}</p>
    <h1 class="text-[26px] leading-tight mt-2">{{ t('home.heroTitle') }}</h1>
    <p class="text-sm text-gray-500 mt-2 max-w-2xl leading-relaxed">{{ t('home.heroSub') }}</p>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-4 mt-6 pt-5 border-t border-line">
      <div class="flex items-start gap-3">
        <svg class="ico text-accent mt-0.5" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 12l3 3 5-6"/></svg>
        <div><div class="text-sm font-medium">{{ t('cap.correct.t') }}</div><div class="text-xs text-gray-400 mt-0.5">{{ t('cap.correct.d') }}</div></div>
      </div>
      <div class="flex items-start gap-3">
        <svg class="ico text-accent mt-0.5" viewBox="0 0 24 24"><path d="M12 3l8 4-8 4-8-4 8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 17l8 4 8-4"/></svg>
        <div><div class="text-sm font-medium">{{ t('cap.version.t') }}</div><div class="text-xs text-gray-400 mt-0.5">{{ t('cap.version.d') }}</div></div>
      </div>
      <div class="flex items-start gap-3">
        <svg class="ico text-accent mt-0.5" viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>
        <div><div class="text-sm font-medium">{{ t('cap.verify.t') }}</div><div class="text-xs text-gray-400 mt-0.5">{{ t('cap.verify.d') }}</div></div>
      </div>
      <div class="flex items-start gap-3">
        <svg class="ico text-accent mt-0.5" viewBox="0 0 24 24"><path d="M8 8l-4 4 4 4"/><path d="M16 8l4 4-4 4"/></svg>
        <div><div class="text-sm font-medium">{{ t('cap.code.t') }}</div><div class="text-xs text-gray-400 mt-0.5">{{ t('cap.code.d') }}</div></div>
      </div>
    </div>
  </section>

  <!-- 工具条：搜索 + 筛选 + 创建（始终可见，即使一无所有） -->
  <div class="flex flex-wrap items-center gap-2 mb-6">
    <input v-model="q" class="input flex-1 min-w-[180px]" :placeholder="t('home.searchDs')" />
    <select v-model="groupFilter" class="input w-auto">
      <option value="">{{ t('home.allGroups') }}</option>
      <option v-for="g in groupOptions" :key="g.slug" :value="g.slug">{{ g.name }}</option>
    </select>
    <button class="btn-primary" @click="showDs = true">＋ {{ t('home.createDataset') }}</button>
    <button class="btn-ghost" @click="showGroup = true">＋ {{ t('home.createGroup2') }}</button>
  </div>

  <!-- 空状态引导 -->
  <div v-if="isEmpty" class="rounded-lg border border-dashed border-line bg-white px-6 py-8 text-center mb-8">
    <p class="text-sm text-gray-500">{{ t('home.emptyHint') }}</p>
    <div class="flex justify-center gap-2 mt-4">
      <button class="btn-primary" @click="showDs = true">＋ {{ t('home.createDataset') }}</button>
      <button class="btn-ghost" @click="showGroup = true">＋ {{ t('home.createGroup2') }}</button>
    </div>
  </div>

  <!-- 近期更新：勘误与版本消息直达对应数据集 -->
  <section v-if="recentFeed.length" class="mb-8">
    <h2 class="text-base text-gray-500 font-normal mb-3 pb-2 border-b border-line">{{ t('home.recentUpdates') }}</h2>
    <div class="rounded-lg border border-line bg-white divide-y divide-line">
      <div v-for="(e,i) in recentFeed" :key="i" class="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-paper cursor-pointer"
           @click="router.push(`/datasets/${e.ds_slug}`)">
        <span class="dot" :style="{ background: evColor(e.type) }"></span>
        <span class="text-gray-800">{{ e.text }}</span>
        <span class="text-gray-400">· {{ e.ds_name }}</span>
        <span class="ml-auto text-xs text-gray-400">{{ e.at }}</span>
      </div>
    </div>
  </section>

  <!-- 我参与的数据集 -->
  <section class="mb-8" v-if="mineShown.length">
    <h2 class="text-base text-gray-500 font-normal mb-3 pb-2 border-b border-line">{{ t('home.myDatasets') }}</h2>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="d in mineShown" :key="d.id" class="card cursor-pointer group flex flex-col"
           @click="router.push(`/datasets/${d.slug}`)">
        <div class="flex items-start justify-between">
          <h3 class="text-base group-hover:text-accent transition">{{ d.name_zh }}</h3>
          <span v-if="d.my_role" class="tag">{{ d.my_role }}</span>
        </div>
        <p class="text-xs text-gray-400 mt-1">
          <span v-if="d.group_name">{{ d.group_name }}</span>
          <span v-else class="italic">{{ t('home.standalone') }}</span>
          <span v-if="d.is_sensitive" class="ml-1 text-accent2">· {{ t('home.sensitive') }}</span>
        </p>
        <p class="text-sm text-gray-500 mt-1.5 line-clamp-2 flex-1">{{ d.desc_zh }}</p>
        <div v-if="d.recent && d.recent.length" class="mt-3 space-y-1">
          <div v-for="(e,i) in d.recent" :key="i" class="flex items-center gap-2 text-xs text-gray-500">
            <span class="dot" :style="{ background: evColor(e.type) }"></span>
            <span>{{ e.text }}</span><span v-if="e.at" class="text-gray-400">· {{ e.at }}</span>
          </div>
        </div>
        <div class="mt-3 pt-3 border-t border-line flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400">
          <span v-if="d.current_version" class="chip-ver">{{ d.current_version }}</span>
          <span>{{ d.member_count }} {{ t('home.members') }}</span>
          <span v-if="d.pending_bugs" class="text-accent2">{{ d.pending_bugs }} {{ t('home.pendingBugs') }}</span>
          <span v-if="d.open_flags" class="text-accent2">{{ d.open_flags }} {{ t('home.openFlags') }}</span>
        </div>
      </div>
    </div>
  </section>

  <!-- 发现数据集 -->
  <section class="mb-8">
    <div class="flex items-center justify-between mb-3 pb-2 border-b border-line">
      <h2 class="text-base text-gray-500 font-normal">{{ t('home.discoverDatasets') }}</h2>
      <span class="text-xs text-gray-400">{{ discoverDs.length }} {{ t('home.datasets') }}</span>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="d in discoverDs" :key="d.id" class="card cursor-pointer group flex flex-col"
           @click="router.push(`/datasets/${d.slug}`)">
        <div class="flex items-start justify-between">
          <h3 class="text-base group-hover:text-accent transition">{{ d.name_zh }}</h3>
          <span v-if="d.is_sensitive" class="tag text-accent2">{{ t('home.sensitive') }}</span>
        </div>
        <p class="text-xs text-gray-400 mt-1">
          <span v-if="d.group_name">{{ d.group_name }}</span>
          <span v-else class="italic">{{ t('home.standalone') }}</span>
        </p>
        <p class="text-sm text-gray-500 mt-1.5 line-clamp-2 flex-1">{{ d.desc_zh }}</p>
        <div class="mt-3 pt-3 border-t border-line flex flex-wrap items-center gap-x-3 text-xs text-gray-400">
          <span v-if="d.current_version" class="chip-ver">{{ d.current_version }}</span>
          <span>{{ d.member_count }} {{ t('home.members') }}</span>
        </div>
      </div>
      <p v-if="!discoverDs.length" class="text-gray-400 text-sm">{{ t('home.noDatasets') }}</p>
    </div>
  </section>

  <!-- 创建数据集（可独立，稍后并入课题组）-->
  <div v-if="showDs" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showDs=false">
    <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
      <h3 class="text-lg mb-1">{{ t('home.createDataset') }}</h3>
      <p class="text-xs text-gray-400 mb-3">{{ t('home.createDsHint') }}</p>
      <input v-model="dsForm.slug" class="input mb-2" placeholder="slug（英文唯一标识）" />
      <input v-model="dsForm.name_zh" class="input mb-2" placeholder="数据集名称" />
      <textarea v-model="dsForm.desc_zh" class="input mb-2" placeholder="简介"></textarea>
      <input v-model="dsForm.founder_contact" class="input mb-2" placeholder="发起人联系方式（必填）" />
      <label class="flex items-center gap-2 text-sm mb-3"><input type="checkbox" v-model="dsForm.is_sensitive" /> 标记为敏感数据集</label>
      <div class="flex justify-end gap-2">
        <button class="btn-ghost" @click="showDs=false">{{ t('common.cancel') }}</button>
        <button class="btn-primary" @click="createDs">{{ t('common.confirm') }}</button>
      </div>
    </div>
  </div>

  <!-- 创建课题组 -->
  <div v-if="showGroup" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showGroup=false">
    <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
      <h3 class="text-lg mb-3">{{ t('home.createGroup2') }}</h3>
      <input v-model="gForm.slug" class="input mb-2" placeholder="slug（英文唯一标识）" />
      <input v-model="gForm.name_zh" class="input mb-2" placeholder="课题组名称" />
      <textarea v-model="gForm.desc_zh" class="input mb-3" placeholder="简介"></textarea>
      <div class="flex justify-end gap-2">
        <button class="btn-ghost" @click="showGroup=false">{{ t('common.cancel') }}</button>
        <button class="btn-primary" @click="createGroup">{{ t('common.confirm') }}</button>
      </div>
    </div>
  </div>
</template>
