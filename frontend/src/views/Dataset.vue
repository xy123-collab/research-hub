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
const lit = ref<any>({ topics: [], refs: [] })
const bugForm = ref({ officer_id: '', variable_id: null, current_value: '', suggested_value: '', description_zh: '' })

const tabs = [
  ['overview', 'ds.overview'], ['dashboard', 'ds.dashboard'], ['versions', 'ds.versions'],
  ['bugs', 'ds.bugs'], ['code', 'ds.code'], ['literature', 'ds.literature'], ['verify', 'ds.verify']
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
}
async function submitBug() {
  try {
    await api.post(`/datasets/${slug}/bugs`, bugForm.value)
    bugForm.value = { officer_id: '', variable_id: null, current_value: '', suggested_value: '', description_zh: '' }
    loadTab('bugs')
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
async function draftFromFlag(id: number) { await api.post(`/verify-flags/${id}/draft-bug`); loadTab('verify') }
function download(v: any, file: string) {
  window.open(`/api/datasets/${slug}/versions/${v.id}/download?file=${file}`, '_blank')
}
const maxBar = (arr:any[]) => Math.max(...arr.map(a=>+a.value), 1)
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
      </div>
      <button v-if="!d.is_member" class="btn-ghost" @click="api.post(`/datasets/${slug}/join-requests`).then(()=>alert('已申请'))">
        {{ t('ds.joinProcess') }}
      </button>
    </div>
    <p v-if="!d.is_member" class="text-xs text-accent2 mt-2">⚠ {{ t('ds.notMemberTip') }}</p>

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
              <td class="py-1"><router-link :to="`/users/${m.user_id}`" class="text-accent">{{ m.name }}</router-link></td>
              <td><span class="tag">{{ m.ds_role }}</span></td>
              <td class="text-gray-400 text-xs">{{ m.joined_at?.slice(0,10) }}</td>
            </tr>
          </table>
        </div>
        <div v-if="d.publications?.length" class="card mt-4">
          <div class="label-cap">近期刊物</div>
          <ul class="text-sm mt-2 list-disc pl-5">
            <li v-for="p in d.publications" :key="p.title">{{ p.title }} · {{ p.venue }} ({{ p.year }})</li>
          </ul>
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
          <p class="text-xs text-gray-400 mt-3">AI/手写描述分析在只读沙箱执行，绝不修改原始值。</p>
        </div>
      </div>

      <!-- versions -->
      <div v-else-if="tab==='versions'">
        <div v-for="v in versions" :key="v.id" class="card mb-3 flex items-center justify-between">
          <div>
            <span class="font-mono">{{ v.version_id }}</span>
            <span v-if="v.is_current" class="tag ml-2">当前</span>
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
          <button class="btn-primary mt-2" @click="submitBug">{{ t('common.submit') }}</button>
        </div>
        <div v-for="b in bugs" :key="b.id" class="card mb-2 flex items-center justify-between">
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
        <div v-for="c in codes" :key="c.id" class="card mb-2">
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
          <div class="label-cap">重点文献清单</div>
          <ul class="text-sm mt-2 list-disc pl-5">
            <li v-for="r in lit.refs" :key="r.id">{{ r.title }} · {{ r.authors }} · {{ r.venue }} ({{ r.year }})</li>
          </ul>
          <p v-if="!lit.refs.length" class="text-gray-400 text-sm">暂无文献。</p>
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
  </div>
</template>
