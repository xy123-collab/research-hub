<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api'

const { t } = useI18n(); const router = useRouter()
const mineDs = ref<any[]>([]); const allDs = ref<any[]>([])
const mineGroups = ref<any[]>([]); const discoverGroups = ref<any[]>([])
const posts = ref<any[]>([])
const q = ref(''); const groupFilter = ref<string>('')
const showGroups = ref(false)
const showCreate = ref(false); const form = ref({ slug: '', name_zh: '', desc_zh: '' })

onMounted(load)
async function load() {
  const [g, mine, wall, ps] = await Promise.all([
    api.get('/groups'),
    api.get('/datasets/mine'),
    api.get('/datasets'),
    api.get('/posts')
  ])
  mineGroups.value = g.data.mine; discoverGroups.value = g.data.discover
  mineDs.value = mine.data
  allDs.value = wall.data
  posts.value = ps.data.slice(0, 4)
}

// 我参与数据集的 id，用于从“发现”里剔除
const mineIds = computed(() => new Set(mineDs.value.map((d: any) => d.id)))
// 课题组筛选下拉：出现在数据集里的所有课题组
const groupOptions = computed(() => {
  const m = new Map<string, string>()
  allDs.value.forEach((d: any) => { if (d.group_slug) m.set(d.group_slug, d.group_name) })
  return [...m.entries()].map(([slug, name]) => ({ slug, name }))
})
function match(d: any) {
  const kw = q.value.trim().toLowerCase()
  const okKw = !kw || `${d.name_zh}${d.desc_zh || ''}${d.group_name || ''}`.toLowerCase().includes(kw)
  const okGroup = !groupFilter.value || d.group_slug === groupFilter.value
  return okKw && okGroup
}
const discoverDs = computed(() =>
  allDs.value.filter((d: any) => !mineIds.value.has(d.id) && match(d)))
const mineDsShown = computed(() => mineDs.value.filter(match))

async function createGroup() {
  await api.post('/groups', form.value); showCreate.value = false
  form.value = { slug: '', name_zh: '', desc_zh: '' }; load()
}
async function joinGroup(slug: string) {
  await api.post(`/groups/${slug}/join-requests`); alert('已提交申请，等待课题组管理员审批')
}
const caps = [
  { icon: '📝', k: 'cap.correct' }, { icon: '🗂️', k: 'cap.version' },
  { icon: '🔍', k: 'cap.verify' }, { icon: '💻', k: 'cap.code' }
]
</script>

<template>
  <!-- 价值 hero + 协作能力条：让“数据协作车间”一眼可见 -->
  <section class="rounded-xl border border-line bg-white px-6 py-6 mb-6">
    <p class="label-cap">{{ t('home.tagline') }}</p>
    <h1 class="text-2xl mt-1">{{ t('home.heroTitle') }}</h1>
    <p class="text-sm text-gray-500 mt-1 max-w-2xl">{{ t('home.heroSub') }}</p>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-5">
      <div v-for="c in caps" :key="c.k" class="rounded-lg border border-line bg-paper px-3 py-3">
        <div class="text-xl">{{ c.icon }}</div>
        <div class="text-sm mt-1 font-medium">{{ t(c.k + '.t') }}</div>
        <div class="text-xs text-gray-500 mt-0.5 leading-snug">{{ t(c.k + '.d') }}</div>
      </div>
    </div>
  </section>

  <!-- 搜索 + 课题组筛选：一步定位任何数据集 -->
  <div class="flex flex-wrap items-center gap-2 mb-5">
    <input v-model="q" class="input flex-1 min-w-[180px]" :placeholder="t('home.searchDs')" />
    <select v-model="groupFilter" class="input w-auto">
      <option value="">{{ t('home.allGroups') }}</option>
      <option v-for="g in groupOptions" :key="g.slug" :value="g.slug">{{ g.name }}</option>
    </select>
  </div>

  <!-- 我的数据集：直达协作，带活跃度信号 -->
  <section class="mb-8" v-if="mineDsShown.length">
    <h2 class="text-xl mb-3">{{ t('home.myDatasets') }}</h2>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="d in mineDsShown" :key="d.id" class="card cursor-pointer"
           @click="router.push(`/datasets/${d.slug}`)">
        <div class="flex items-start justify-between">
          <div class="text-2xl">{{ d.icon || '📊' }}</div>
          <span v-if="d.my_role" class="tag">{{ d.my_role }}</span>
        </div>
        <h3 class="mt-2">{{ d.name_zh }}
          <span v-if="d.is_sensitive" class="tag border-accent2 text-accent2">敏感</span></h3>
        <p class="text-xs text-gray-400 mt-1">{{ d.group_name }}</p>
        <p class="text-sm text-gray-500 mt-1 line-clamp-2">{{ d.desc_zh }}</p>
        <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400">
          <span v-if="d.current_version" class="font-mono text-accent">{{ d.current_version }}</span>
          <span>{{ d.member_count }} {{ t('home.members') }}</span>
          <span v-if="d.pending_bugs" class="text-accent2">● {{ d.pending_bugs }} {{ t('home.pendingBugs') }}</span>
          <span v-if="d.open_flags" class="text-accent2">● {{ d.open_flags }} {{ t('home.openFlags') }}</span>
        </div>
      </div>
    </div>
  </section>

  <!-- 发现数据集：全平台，跨课题组直接浏览 -->
  <section class="mb-8">
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-xl">{{ t('home.discoverDatasets') }}</h2>
      <span class="text-xs text-gray-400">{{ discoverDs.length }} {{ t('home.datasets') }}</span>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="d in discoverDs" :key="d.id" class="card cursor-pointer"
           @click="router.push(`/datasets/${d.slug}`)">
        <div class="text-2xl">{{ d.icon || '📊' }}</div>
        <h3 class="mt-2">{{ d.name_zh }}
          <span v-if="d.is_sensitive" class="tag border-accent2 text-accent2">敏感</span></h3>
        <p class="text-xs text-gray-400 mt-1">{{ d.group_name }}</p>
        <p class="text-sm text-gray-500 mt-1 line-clamp-2">{{ d.desc_zh }}</p>
        <div class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400">
          <span v-if="d.current_version" class="font-mono text-accent">{{ d.current_version }}</span>
          <span>{{ d.member_count }} {{ t('home.members') }}</span>
        </div>
      </div>
      <p v-if="!discoverDs.length" class="text-gray-400 text-sm">{{ t('home.noDatasets') }}</p>
    </div>
  </section>

  <!-- 课题组：治理与归属层，降为可展开的次级区块 -->
  <section class="mb-8">
    <button class="flex items-center gap-2 text-xl mb-1" @click="showGroups = !showGroups">
      <span>{{ t('home.groupsSection') }}</span>
      <span class="text-sm text-gray-400">{{ showGroups ? '▾' : '▸' }} {{ mineGroups.length }}/{{ mineGroups.length + discoverGroups.length }}</span>
    </button>
    <p class="text-xs text-gray-400 mb-3">{{ t('home.groupsHint') }}</p>
    <div v-show="showGroups">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-sm text-gray-500">{{ t('home.myGroups') }}</h3>
        <button class="btn-ghost text-xs" @click="showCreate = true">{{ t('home.createGroup') }}</button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <div v-for="g in mineGroups" :key="g.id" class="card cursor-pointer py-4"
             @click="router.push(`/groups/${g.slug}`)">
          <div class="flex items-center gap-2">
            <span class="text-xl">{{ g.icon || '🏛️' }}</span>
            <h3 class="text-base">{{ g.name_zh }}</h3>
          </div>
          <div class="mt-2 text-xs text-gray-400 flex gap-3">
            <span>{{ g.member_count }} {{ t('home.members') }}</span>
            <span>{{ g.dataset_count }} {{ t('home.datasets') }}</span>
            <span v-if="g.my_role" class="tag">{{ g.my_role }}</span>
          </div>
        </div>
        <p v-if="!mineGroups.length" class="text-gray-400 text-sm">{{ t('home.noGroups') }}</p>
      </div>
      <h3 class="text-sm text-gray-500 mb-2">{{ t('home.discover') }}</h3>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div v-for="g in discoverGroups" :key="g.id" class="card py-4">
          <div class="flex items-center gap-2">
            <span class="text-xl">{{ g.icon || '🏛️' }}</span>
            <h3 class="text-base">{{ g.name_zh }}</h3>
          </div>
          <div class="mt-2 flex items-center justify-between">
            <span class="text-xs text-gray-400">{{ g.member_count }} {{ t('home.members') }}</span>
            <button class="btn-ghost text-xs" @click.stop="joinGroup(g.slug)">{{ t('home.join') }}</button>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- 研究广场近期 -->
  <section v-if="posts.length">
    <h2 class="text-xl mb-3">{{ t('home.recent') }}</h2>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div v-for="p in posts" :key="p.id" class="card">
        <div class="flex items-center gap-2 text-sm">
          <span class="text-lg">{{ p.cover_icon || '💡' }}</span>
          <router-link :to="`/users/${p.author_id}`" class="text-accent hover:underline">{{ p.author_name }}</router-link>
        </div>
        <p class="mt-2 text-sm">{{ p.content_zh }}</p>
        <div class="mt-2 flex gap-1"><span v-for="tag in p.tags" :key="tag" class="tag">{{ tag }}</span></div>
      </div>
    </div>
  </section>

  <div v-if="showCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
      <h3 class="text-lg mb-3">创建课题组</h3>
      <input v-model="form.slug" class="input mb-2" placeholder="slug（英文唯一标识）" />
      <input v-model="form.name_zh" class="input mb-2" placeholder="课题组名称" />
      <textarea v-model="form.desc_zh" class="input mb-3" placeholder="简介"></textarea>
      <div class="flex justify-end gap-2">
        <button class="btn-ghost" @click="showCreate=false">{{ t('common.cancel') }}</button>
        <button class="btn-primary" @click="createGroup">{{ t('common.confirm') }}</button>
      </div>
    </div>
  </div>
</template>
