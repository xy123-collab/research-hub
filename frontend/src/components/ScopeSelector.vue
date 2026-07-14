<script setup lang="ts">
// 统一「可见范围」选择器：全平台公开 / 课题组成员可见 / 数据集成员可见 / 仅自己可见。
// 选课题组或数据集时，可从「我所在的组/集」勾选「多个」。
// 用 v-model 绑定 { scope, scope_ref_ids }。
import { ref, onMounted, watch } from 'vue'
import api from '../api'

const props = defineProps<{ modelValue: { scope: string; scope_ref_ids: number[] } }>()
const emit = defineEmits(['update:modelValue'])

const scope = ref(props.modelValue?.scope || 'public')
const refIds = ref<number[]>(props.modelValue?.scope_ref_ids ? [...props.modelValue.scope_ref_ids] : [])
const groups = ref<any[]>([]); const datasets = ref<any[]>([])

const OPTIONS = [
  { v: 'public', label: '全平台公开' },
  { v: 'group', label: '课题组成员可见' },
  { v: 'dataset', label: '数据集成员可见' },
  { v: 'self', label: '仅自己可见' }
]

onMounted(async () => {
  try {
    const r = (await api.get('/me/collab-scopes')).data
    groups.value = r.groups || []; datasets.value = r.datasets || []
  } catch {}
})

function emitVal() { emit('update:modelValue', { scope: scope.value, scope_ref_ids: [...refIds.value] }) }
function toggle(id: number) {
  const i = refIds.value.indexOf(id)
  if (i >= 0) refIds.value.splice(i, 1); else refIds.value.push(id)
  emitVal()
}
watch(scope, () => { refIds.value = []; emitVal() })
</script>
<template>
  <div>
    <label class="label-cap">可见范围</label>
    <select v-model="scope" class="input">
      <option v-for="o in OPTIONS" :key="o.v" :value="o.v">{{ o.label }}</option>
    </select>

    <div v-if="scope==='group'" class="mt-2 border border-line rounded p-2 max-h-32 overflow-y-auto">
      <p v-if="!groups.length" class="text-xs text-gray-400">你还没有加入任何课题组</p>
      <label v-for="g in groups" :key="g.id" class="flex items-center gap-2 text-sm py-0.5">
        <input type="checkbox" :checked="refIds.includes(g.id)" @change="toggle(g.id)" />
        <span>{{ g.name }} <span class="text-gray-400 text-xs">ID {{ g.id }}</span></span>
      </label>
      <p class="text-[11px] text-gray-400 mt-1">可多选；对勾选课题组的成员可见。</p>
    </div>

    <div v-if="scope==='dataset'" class="mt-2 border border-line rounded p-2 max-h-32 overflow-y-auto">
      <p v-if="!datasets.length" class="text-xs text-gray-400">你还没有加入任何数据集</p>
      <label v-for="d in datasets" :key="d.id" class="flex items-center gap-2 text-sm py-0.5">
        <input type="checkbox" :checked="refIds.includes(d.id)" @change="toggle(d.id)" />
        <span>{{ d.name }} <span class="text-gray-400 text-xs">ID {{ d.id }}</span></span>
      </label>
      <p class="text-[11px] text-gray-400 mt-1">可多选；对勾选数据集的成员可见。</p>
    </div>
  </div>
</template>
