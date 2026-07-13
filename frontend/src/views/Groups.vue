<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api'

const { t } = useI18n(); const router = useRouter()
const mine = ref<any[]>([]); const discover = ref<any[]>([])
const showCreate = ref(false); const form = ref({ slug: '', name_zh: '', desc_zh: '' })

onMounted(load)
async function load() {
  const g = (await api.get('/groups')).data
  mine.value = g.mine; discover.value = g.discover
}
async function createGroup() {
  if (!form.value.slug || !form.value.name_zh) { alert('请填写标识与名称'); return }
  await api.post('/groups', form.value); showCreate.value = false
  form.value = { slug: '', name_zh: '', desc_zh: '' }; load()
}
async function joinGroup(slug: string) {
  await api.post(`/groups/${slug}/join-requests`); alert('已提交申请，等待课题组管理员审批')
}
</script>

<template>
  <div class="flex items-end justify-between mb-6">
    <div>
      <p class="text-[11px] uppercase tracking-[0.18em] text-gray-400">Research Groups</p>
      <h1 class="text-2xl mt-1">{{ t('nav.groups') }}</h1>
      <p class="text-sm text-gray-500 mt-1">{{ t('home.groupsHint') }}</p>
    </div>
    <button class="btn-primary" @click="showCreate = true">{{ t('home.createGroup') }}</button>
  </div>

  <section class="mb-8">
    <h2 class="text-base text-gray-500 font-normal mb-3 pb-2 border-b border-line">{{ t('home.myGroups') }}</h2>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="g in mine" :key="g.id" class="card cursor-pointer group"
           @click="router.push(`/groups/${g.slug}`)">
        <div class="flex items-center justify-between">
          <h3 class="text-base group-hover:text-accent transition">{{ g.name_zh }}</h3>
          <span v-if="g.my_role" class="tag">{{ g.my_role }}</span>
        </div>
        <p class="text-sm text-gray-500 mt-1 line-clamp-2">{{ g.desc_zh }}</p>
        <div class="mt-4 pt-3 border-t border-line text-xs text-gray-400 flex gap-4">
          <span>{{ g.member_count }} {{ t('home.members') }}</span>
          <span>{{ g.dataset_count }} {{ t('home.datasets') }}</span>
        </div>
      </div>
      <p v-if="!mine.length" class="text-gray-400 text-sm">{{ t('home.noGroups') }}</p>
    </div>
  </section>

  <section>
    <h2 class="text-base text-gray-500 font-normal mb-3 pb-2 border-b border-line">{{ t('home.discover') }}</h2>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="g in discover" :key="g.id" class="card">
        <h3 class="text-base">{{ g.name_zh }}</h3>
        <p class="text-sm text-gray-500 mt-1 line-clamp-2">{{ g.desc_zh }}</p>
        <div class="mt-4 pt-3 border-t border-line flex items-center justify-between">
          <span class="text-xs text-gray-400">{{ g.member_count }} {{ t('home.members') }}</span>
          <button class="btn-ghost text-xs" @click="joinGroup(g.slug)">{{ t('home.join') }}</button>
        </div>
      </div>
      <p v-if="!discover.length" class="text-gray-400 text-sm">—</p>
    </div>
  </section>

  <div v-if="showCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50" @click.self="showCreate=false">
    <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
      <h3 class="text-lg mb-3">{{ t('home.createGroup') }}</h3>
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
