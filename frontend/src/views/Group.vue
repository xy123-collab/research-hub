<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api'
import CharterModal from '../components/CharterModal.vue'

const route = useRoute(); const router = useRouter(); const { t } = useI18n()
const g = ref<any>(null)
const showDs = ref(false); const dsForm = ref({ slug: '', name_zh: '', desc_zh: '', founder_contact: '' })

onMounted(load)
watch(() => route.params.slug, load)
async function load() { g.value = (await api.get(`/groups/${route.params.slug}`)).data }
async function createDs() {
  if (!dsForm.value.founder_contact) { alert('发起人联系方式必填'); return }
  await api.post(`/groups/${route.params.slug}/datasets`, dsForm.value)
  showDs.value = false; load()
}
async function join() { await api.post(`/groups/${route.params.slug}/join-requests`); alert('已提交申请') }
</script>
<template>
  <div v-if="g">
    <CharterModal v-if="g.is_member" scope="group" :refId="g.id" />
    <div class="flex items-start justify-between">
      <div>
        <h1 class="text-2xl">{{ g.icon }} {{ g.name_zh }}</h1>
        <p class="text-gray-500 mt-1">{{ g.desc_zh }}</p>
        <div class="mt-2 text-xs text-gray-400">{{ g.member_count }} {{ t('home.members') }}</div>
      </div>
      <button v-if="!g.is_member" class="btn-ghost" @click="join">{{ t('home.join') }}</button>
    </div>

    <div v-if="g.charter" class="card mt-5 bg-paper">
      <div class="label-cap">公约 · v{{ g.charter.version }}</div>
      <pre class="whitespace-pre-wrap bg-white text-ink border border-line mt-2">{{ g.charter.body_zh }}</pre>
    </div>

    <section class="mt-6">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-xl">{{ t('ds.overview') }} · 数据集</h2>
        <button v-if="g.is_member" class="btn-primary" @click="showDs=true">＋发起新数据集</button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div v-for="d in g.datasets" :key="d.id" class="card cursor-pointer" @click="router.push(`/datasets/${d.slug}`)">
          <div class="text-2xl">{{ d.icon || '📊' }}</div>
          <h3 class="mt-2">{{ d.name_zh }}</h3>
        </div>
        <p v-if="!g.datasets.length" class="text-gray-400 text-sm">本组暂无数据集。</p>
      </div>
    </section>

    <div v-if="showDs" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
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
