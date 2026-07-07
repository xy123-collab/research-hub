<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api'

const { t } = useI18n(); const router = useRouter()
const mine = ref<any[]>([]); const discover = ref<any[]>([]); const posts = ref<any[]>([])
const showCreate = ref(false); const form = ref({ slug: '', name_zh: '', desc_zh: '' })

onMounted(load)
async function load() {
  const g = (await api.get('/groups')).data
  mine.value = g.mine; discover.value = g.discover
  posts.value = (await api.get('/posts')).data.slice(0, 6)
}
async function createGroup() {
  await api.post('/groups', form.value); showCreate.value = false
  form.value = { slug: '', name_zh: '', desc_zh: '' }; load()
}
async function joinGroup(slug: string) {
  await api.post(`/groups/${slug}/join-requests`); alert('已提交申请，等待课题组管理员审批')
}
</script>
<template>
  <section class="mb-8">
    <div class="flex items-center justify-between mb-3">
      <h2 class="text-xl">{{ t('home.myGroups') }}</h2>
      <button class="btn-primary" @click="showCreate = true">{{ t('home.createGroup') }}</button>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="g in mine" :key="g.id" class="card cursor-pointer" @click="router.push(`/groups/${g.slug}`)">
        <div class="text-2xl">{{ g.icon || '🏛️' }}</div>
        <h3 class="mt-2">{{ g.name_zh }}</h3>
        <p class="text-sm text-gray-500 mt-1 line-clamp-2">{{ g.desc_zh }}</p>
        <div class="mt-3 text-xs text-gray-400 flex gap-3">
          <span>{{ g.member_count }} {{ t('home.members') }}</span>
          <span>{{ g.dataset_count }} {{ t('home.datasets') }}</span>
          <span v-if="g.my_role" class="tag">{{ g.my_role }}</span>
        </div>
      </div>
      <p v-if="!mine.length" class="text-gray-400 text-sm">还没有加入课题组，去下方发现或创建一个。</p>
    </div>
  </section>

  <section class="mb-8">
    <h2 class="text-xl mb-3">{{ t('home.discover') }}</h2>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="g in discover" :key="g.id" class="card">
        <div class="text-2xl">{{ g.icon || '🏛️' }}</div>
        <h3 class="mt-2">{{ g.name_zh }}</h3>
        <p class="text-sm text-gray-500 mt-1 line-clamp-2">{{ g.desc_zh }}</p>
        <div class="mt-3 flex items-center justify-between">
          <span class="text-xs text-gray-400">{{ g.member_count }} {{ t('home.members') }}</span>
          <button class="btn-ghost text-xs" @click="joinGroup(g.slug)">{{ t('home.join') }}</button>
        </div>
      </div>
    </div>
  </section>

  <section>
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
