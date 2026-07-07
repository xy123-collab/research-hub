<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api'

const { t } = useI18n()
const posts = ref<any[]>([])
const form = ref({ content_zh: '', visibility: 'platform', tags: '' })

onMounted(load)
async function load() { posts.value = (await api.get('/posts')).data }
async function submit() {
  if (!form.value.content_zh) return
  await api.post('/posts', { content_zh: form.value.content_zh, visibility: form.value.visibility,
    tags: form.value.tags ? form.value.tags.split(',').map(s=>s.trim()) : [] })
  form.value = { content_zh: '', visibility: 'platform', tags: '' }; load()
}
async function like(p: any) { await api.post(`/posts/${p.id}/react`, null, { params: { type: 'like' } }); load() }
</script>
<template>
  <h1 class="text-2xl mb-4">{{ t('nav.feed') }}</h1>
  <div class="card mb-6">
    <textarea v-model="form.content_zh" class="input" placeholder="分享一个研究想法…"></textarea>
    <div class="flex items-center gap-2 mt-2">
      <select v-model="form.visibility" class="input w-40">
        <option value="platform">{{ t('feed.platform') }}</option>
        <option value="group">{{ t('feed.group') }}</option>
        <option value="private">{{ t('feed.private') }}</option>
      </select>
      <input v-model="form.tags" class="input" placeholder="标签（逗号分隔，如 COD）" />
      <button class="btn-primary" @click="submit">{{ t('feed.post') }}</button>
    </div>
  </div>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div v-for="p in posts" :key="p.id" class="card">
      <div class="flex items-center gap-2 text-sm">
        <span class="text-lg">{{ p.cover_icon || '💡' }}</span>
        <router-link :to="`/users/${p.author_id}`" class="text-accent hover:underline">{{ p.author_name }}</router-link>
        <span class="tag ml-auto">{{ p.visibility }}</span>
      </div>
      <p class="mt-2 text-sm">{{ p.content_zh }}</p>
      <div class="mt-2 flex items-center gap-2">
        <span v-for="tag in p.tags" :key="tag" class="tag">{{ tag }}</span>
        <button class="text-xs text-gray-500 ml-auto hover:text-accent" @click="like(p)">♥ {{ p.likes }}</button>
      </div>
    </div>
  </div>
</template>
