<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const projects = ref<any[]>([])
const q = ref('')
const showCreate = ref(false)
const form = ref({ name_zh: '', desc_zh: '' })
const saving = ref(false)

onMounted(load)
async function load() {
  projects.value = (await api.get('/groups')).data.mine || []
}
const shown = computed(() => {
  const kw = q.value.trim().toLowerCase()
  if (!kw) return projects.value
  return projects.value.filter((p: any) =>
    [p.id, p.slug, p.name_zh, p.desc_zh].some(x => String(x || '').toLowerCase().includes(kw)))
})
function roleName(role: string) {
  return role === 'group_owner' ? 'Owner' : role === 'group_admin' ? 'Admin' : 'Member'
}
async function createProject() {
  if (!form.value.name_zh.trim()) return alert('请填写研究项目名称')
  saving.value = true
  try {
    const res = await api.post('/groups', form.value)
    showCreate.value = false
    form.value = { name_zh: '', desc_zh: '' }
    router.push(`/groups/${res.data.slug}`)
  } catch (e: any) {
    alert(e.response?.data?.detail || '创建失败')
  } finally { saving.value = false }
}
</script>

<template>
  <div class="flex items-end justify-between mb-6 gap-4">
    <div>
      <p class="eyebrow">Private Research Workspace</p>
      <h1 class="text-2xl mt-1">研究项目</h1>
      <p class="text-sm text-gray-500 mt-1">仅展示你参与的私密项目，用于共享进展、资料与关键问题。</p>
    </div>
    <button class="btn-primary shrink-0" @click="showCreate=true">＋ 创建研究项目</button>
  </div>

  <input v-model="q" class="input mb-6" placeholder="搜索我的研究项目" />

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <article v-for="p in shown" :key="p.id" class="card cursor-pointer group"
             @click="router.push(`/groups/${p.slug}`)">
      <div class="flex items-start justify-between gap-3">
        <h2 class="text-base group-hover:text-accent transition">{{ p.name_zh }}</h2>
        <span class="tag">{{ roleName(p.my_role) }}</span>
      </div>
      <p class="text-xs text-gray-300 mt-1">研究项目 ID {{ p.id }}</p>
      <p class="text-sm text-gray-500 mt-2 line-clamp-3">{{ p.desc_zh || '暂无项目介绍' }}</p>
      <div class="mt-4 pt-3 border-t border-line text-xs text-gray-400 flex gap-4">
        <span>{{ p.member_count }} 位成员</span>
        <span>{{ p.dataset_count }} 个内部数据集</span>
      </div>
    </article>
  </div>
  <div v-if="!shown.length" class="card text-center text-gray-400 py-12">
    {{ q ? '没有匹配的研究项目。' : '你还没有参与研究项目。创建一个，或等待总管理员/管理员邀请。' }}
  </div>

  <div v-if="showCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
      <h3 class="text-lg mb-1">创建研究项目</h3>
      <p class="text-xs text-gray-500 mb-4">研究项目默认私密，创建后你自动成为总管理员。</p>
      <input v-model="form.name_zh" class="input mb-2" placeholder="项目名称" />
      <textarea v-model="form.desc_zh" class="input mb-3" rows="4" placeholder="项目介绍、研究问题或协作目标"></textarea>
      <div class="flex justify-end gap-2">
        <button class="btn-ghost" @click="showCreate=false">取消</button>
        <button class="btn-primary" :disabled="saving" @click="createProject">{{ saving ? '创建中…' : '创建' }}</button>
      </div>
    </div>
  </div>
</template>
