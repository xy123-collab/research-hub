<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
import Icon from '../components/Icon.vue'
const skills = ref<any[]>([]); const recos = ref<any[]>([])
const show = ref(false); const form = ref({ name_zh: '', desc_zh: '', github_url: '' })
onMounted(load)
async function load() {
  skills.value = (await api.get('/skills')).data
  recos.value = (await api.get('/github-skill-recos')).data
}
async function create() {
  try { await api.post('/skills', form.value); show.value=false; form.value={name_zh:'',desc_zh:'',github_url:''}; load() }
  catch(e:any){ alert(e.response?.data?.detail || '失败') }
}
</script>
<template>
  <div class="flex items-center justify-between mb-4">
    <h1 class="text-2xl">科研 Skill 共享</h1>
    <button class="btn-primary" @click="show=true">＋发起 Skill</button>
  </div>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div v-for="s in skills" :key="s.id" class="card">
      <h3 class="flex items-center gap-2"><Icon name="puzzle" class="ico text-accent" /> {{ s.name_zh }}</h3>
      <p class="text-sm text-gray-500 mt-1">{{ s.desc_zh }}</p>
      <a v-if="s.github_url" :href="s.github_url" target="_blank" class="text-accent text-xs mt-2 inline-block">GitHub ↗</a>
    </div>
    <p v-if="!skills.length" class="text-gray-400 text-sm">暂无 Skill。</p>
  </div>
  <h2 class="text-lg mt-8 mb-3">GitHub 推荐 Skill</h2>
  <ul class="text-sm space-y-1">
    <li v-for="r in recos" :key="r.id"><a :href="r.github_url" target="_blank" class="text-accent">{{ r.name }} ↗</a> · {{ r.note }}</li>
  </ul>
  <div v-if="show" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
      <h3 class="text-lg mb-3">发起 Skill</h3>
      <input v-model="form.name_zh" class="input mb-2" placeholder="名称" />
      <textarea v-model="form.desc_zh" class="input mb-2" placeholder="简介"></textarea>
      <input v-model="form.github_url" class="input mb-3" placeholder="GitHub 链接（可选）" />
      <div class="flex justify-end gap-2">
        <button class="btn-ghost" @click="show=false">取消</button>
        <button class="btn-primary" @click="create">确认</button>
      </div>
    </div>
  </div>
</template>
