<script setup lang="ts">
// 可复用的 @提及 输入框：输入 @ 触发候选下拉，可@整个数据集/课题组或范围内单个成员，
// 支持关键词检索名称/ID。选中后把 @名称 写入文本，并记录结构化 mentions 供后端按范围校验。
import { ref, watch, nextTick } from 'vue'
import api from '../api'

const props = defineProps<{ modelValue: string; placeholder?: string; rows?: number }>()
const emit = defineEmits(['update:modelValue', 'update:mentions', 'enter'])

const text = ref(props.modelValue || '')
const picked = ref<any[]>([])          // 已选 @对象：{target_type,target_id,label}
watch(() => props.modelValue, v => { if (v !== text.value) text.value = v || '' })

const open = ref(false)
const query = ref('')
const scopes = ref<any[]>([])
const members = ref<any[]>([])
const atPos = ref(-1)                   // 触发@的位置
const ta = ref<HTMLTextAreaElement | null>(null)
const loading = ref(false)
let timer: any = null

function onInput(e: any) {
  text.value = e.target.value
  emit('update:modelValue', text.value)
  syncMentions()
  const pos = e.target.selectionStart
  const before = text.value.slice(0, pos)
  const m = /@([^\s@]{0,20})$/.exec(before)
  if (m) {
    atPos.value = pos - m[1].length - 1
    query.value = m[1]
    open.value = true
    debounceSearch()
  } else {
    open.value = false
  }
}
function debounceSearch() {
  clearTimeout(timer)
  timer = setTimeout(search, 180)
}
async function search() {
  loading.value = true
  try {
    const r = (await api.get('/mentions/candidates', { params: { q: query.value } })).data
    scopes.value = r.scopes || []
    members.value = r.members || []
  } catch { scopes.value = []; members.value = [] }
  finally { loading.value = false }
}
function pick(entry: any) {
  const label = entry.target_type === 'user'
    ? (entry.display_name || entry.username)
    : (entry.name + '(全体)')
  const token = '@' + label + ' '
  const pre = text.value.slice(0, atPos.value)
  const post = text.value.slice(atPos.value + 1 + query.value.length)
  text.value = pre + token + post
  emit('update:modelValue', text.value)
  picked.value.push({ target_type: entry.target_type, target_id: entry.target_id, label })
  emit('update:mentions', picked.value)
  open.value = false
  nextTick(() => ta.value?.focus())
}
// 若用户删掉了某个 @名称，就把对应 mention 去掉
function syncMentions() {
  picked.value = picked.value.filter(p => text.value.includes('@' + p.label))
  emit('update:mentions', picked.value)
}
function onEnter(e: any) {
  if (open.value) { e.preventDefault(); return }
  emit('enter')
}
function reset() { text.value = ''; picked.value = []; emit('update:modelValue', ''); emit('update:mentions', []) }
defineExpose({ reset })
</script>
<template>
  <div class="relative">
    <textarea ref="ta" :value="text" :rows="rows || 2"
      class="input text-sm w-full resize-y" :placeholder="placeholder || '写评论…（输入 @ 提及成员）'"
      @input="onInput" @keydown.enter="onEnter"></textarea>
    <div v-if="open" class="absolute z-30 left-0 right-0 mt-1 bg-white border border-line rounded shadow-lg max-h-60 overflow-auto text-sm">
      <div v-if="loading" class="px-3 py-2 text-gray-400">检索中…</div>
      <template v-else>
        <div v-if="scopes.length" class="px-3 pt-2 pb-1 text-xs text-gray-400">@整个数据集/课题组</div>
        <button v-for="s in scopes" :key="s.target_type + s.target_id" type="button"
          class="w-full text-left px-3 py-1.5 hover:bg-paper flex items-center gap-2"
          @mousedown.prevent="pick(s)">
          <span class="tag" :style="s.kind==='dataset' ? 'background:#eef2f8;color:#2d4a7c' : 'background:#e6f4ea;color:#2f7d46'">
            {{ s.kind==='dataset' ? '数据集' : '课题组' }}</span>
          <span>{{ s.name }}（全体成员）</span>
        </button>
        <div v-if="members.length" class="px-3 pt-2 pb-1 text-xs text-gray-400">成员</div>
        <button v-for="m in members" :key="'u'+m.target_id" type="button"
          class="w-full text-left px-3 py-1.5 hover:bg-paper"
          @mousedown.prevent="pick(m)">
          <span class="text-accent">{{ m.display_name || m.username }}</span>
          <span class="text-gray-400 text-xs ml-1">#{{ m.target_id }}</span>
          <span v-if="m.scopes && m.scopes.length" class="text-gray-400 text-xs ml-2">
            {{ m.scopes.map((x:any)=>x.name).join(' / ') }}</span>
        </button>
        <div v-if="!scopes.length && !members.length" class="px-3 py-2 text-gray-400">未找到匹配成员</div>
      </template>
    </div>
  </div>
</template>
