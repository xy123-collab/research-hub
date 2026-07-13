<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api'
import CharterModal from '../components/CharterModal.vue'

const route = useRoute(); const router = useRouter(); const { t } = useI18n()
const g = ref<any>(null)
const activity = ref<any[]>([]); const requests = ref<any[]>([])
const showDs = ref(false); const dsForm = ref({ slug: '', name_zh: '', desc_zh: '', founder_contact: '' })

onMounted(load)
watch(() => route.params.slug, load)
async function load() {
  g.value = (await api.get(`/groups/${route.params.slug}`)).data
  activity.value = (await api.get(`/groups/${route.params.slug}/activity`)).data
  if (g.value.is_admin) {
    try { requests.value = (await api.get(`/groups/${route.params.slug}/dataset-requests`)).data } catch {}
  }
}
async function createDs() {
  if (!dsForm.value.founder_contact) { alert('发起人联系方式必填'); return }
  await api.post(`/groups/${route.params.slug}/datasets`, dsForm.value)
  showDs.value = false; load()
}
async function join() { await api.post(`/groups/${route.params.slug}/join-requests`); alert('已提交申请') }
async function decideReq(id: number, approve: boolean) {
  await api.post(`/dataset-group-requests/${id}/decide`, null, { params: { approve } }); load()
}
const evColor = (x: string) => x === 'version' ? '#2d4a7c' : x === 'post' ? '#4b5563' : '#7c2d3a'
const evLabel = (x: string) => x === 'version' ? '版本' : x === 'post' ? '发帖' : '勘误'
</script>

<template>
  <div v-if="g">
    <CharterModal v-if="g.is_member" scope="group" :refId="g.id" />

    <div class="flex items-start justify-between">
      <div>
        <p class="eyebrow">Research Group</p>
        <h1 class="text-2xl mt-1">{{ g.name_zh }}</h1>
        <p class="text-gray-500 mt-1">{{ g.desc_zh }}</p>
        <div class="mt-2 text-xs text-gray-400">{{ g.member_count }} {{ t('home.members') }}</div>
      </div>
      <button v-if="!g.is_member" class="btn-ghost" @click="join">{{ t('home.join') }}</button>
    </div>

    <div v-if="g.charter" class="card mt-5">
      <div class="label-cap">{{ t('grp.charter') }} · v{{ g.charter.version }}</div>
      <pre class="whitespace-pre-wrap bg-white text-ink border border-line mt-2">{{ g.charter.body_zh }}</pre>
    </div>

    <!-- 数据集归属申请（仅课题组管理员可见） -->
    <section v-if="g.is_admin && requests.length" class="mt-6">
      <h2 class="text-base text-gray-500 font-normal mb-3 pb-2 border-b border-line">{{ t('grp.requests') }}</h2>
      <div class="rounded-lg border border-line bg-white divide-y divide-line">
        <div v-for="r in requests" :key="r.id" class="flex items-center gap-3 px-4 py-3 text-sm">
          <span class="tag">{{ r.kind === 'attach' ? t('grp.attachReq') : t('grp.detachReq') }}</span>
          <span class="font-medium">{{ r.dataset_name }}</span>
          <span class="text-gray-400">· {{ r.requested_by }}</span>
          <div class="ml-auto flex gap-2">
            <button class="btn-primary text-xs" @click="decideReq(r.id, true)">{{ t('grp.approve') }}</button>
            <button class="btn-ghost text-xs" @click="decideReq(r.id, false)">{{ t('grp.reject') }}</button>
          </div>
        </div>
      </div>
    </section>

    <div class="grid md:grid-cols-3 gap-6 mt-6">
      <!-- 数据集网格 -->
      <section class="md:col-span-2">
        <div class="flex items-center justify-between mb-3 pb-2 border-b border-line">
          <h2 class="text-base text-gray-500 font-normal">{{ t('grp.datasets') }}</h2>
          <button v-if="g.is_member" class="btn-ghost text-xs" @click="showDs=true">＋ {{ t('ds.overview') }}</button>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div v-for="d in g.datasets" :key="d.id" class="card cursor-pointer group"
               @click="router.push(`/datasets/${d.slug}`)">
            <h3 class="text-base group-hover:text-accent transition">{{ d.name_zh }}</h3>
          </div>
          <p v-if="!g.datasets.length" class="text-gray-400 text-sm">本组暂无数据集。</p>
        </div>
      </section>

      <!-- 组内动态 -->
      <section>
        <h2 class="text-base text-gray-500 font-normal mb-3 pb-2 border-b border-line">{{ t('grp.activity') }}</h2>
        <div class="rounded-lg border border-line bg-white divide-y divide-line">
          <div v-for="(e,i) in activity" :key="i"
               class="px-4 py-2.5 text-sm flex items-start gap-2"
               :class="e.type==='version' ? 'cursor-pointer hover:bg-paper' : ''"
               @click="e.type==='version' && e.ref && router.push(`/datasets/${e.ref}`)">
            <span class="dot mt-1.5" :style="{ background: evColor(e.type) }"></span>
            <div class="min-w-0">
              <div class="text-gray-800 truncate">{{ e.title }}</div>
              <div class="text-xs text-gray-400">{{ evLabel(e.type) }} · {{ e.who }}<span v-if="e.at"> · {{ (e.at||'').slice(0,10) }}</span></div>
            </div>
          </div>
          <p v-if="!activity.length" class="px-4 py-3 text-gray-400 text-sm">{{ t('grp.noActivity') }}</p>
        </div>
      </section>
    </div>

    <div v-if="showDs" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showDs=false">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-3">发起新数据集</h3>
        <input v-model="dsForm.slug" class="input mb-2" placeholder="slug" />
        <input v-model="dsForm.name_zh" class="input mb-2" placeholder="数据集名称" />
        <textarea v-model="dsForm.desc_zh" class="input mb-2" placeholder="简介"></textarea>
        <input v-model="dsForm.founder_contact" class="input mb-3" placeholder="发起人联系方式（必填）" />
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showDs=false">{{ t('common.cancel') }}</button>
          <button class="btn-primary" @click="createDs">{{ t('common.confirm') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
