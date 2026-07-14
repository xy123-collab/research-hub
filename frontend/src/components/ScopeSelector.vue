<script setup lang="ts">
// 统一「可见范围」选择器：全平台公开 / 课题组成员可见 / 数据集成员可见 / 仅自己可见。
// 选课题组或数据集时，从「我所在的组/集」下拉选择具体一个。
// 用 v-model 绑定 { scope, scope_ref_id }。
import { ref, onMounted, watch } from 'vue'
import api from '../api'

const props = defineProps<{ modelValue: { scope: string; scope_ref_id: number | null } }>()
const emit = defineEmits(['update:modelValue'])

const scope = ref(props.modelValue?.scope || 'public')
const refId = ref<number | null>(props.modelValue?.scope_ref_id ?? null)
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

function emitVal() { emit('update:modelValue', { scope: scope.value, scope_ref_id: refId.value }) }
watch(scope, (v) => {
  if (v !== 'group' && v !== 'dataset') refId.value = null
  else {
    const list = v === 'group' ? groups.value : datasets.value
    refId.value = list.length ? list[0].id : null
  }
  emitVal()
})
watch(refId, emitVal)
</script>
<template>
  <div>
    <label class="label-cap">可见范围</label>
    <select v-model="scope" class="input">
      <option v-for="o in OPTIONS" :key="o.v" :value="o.v">{{ o.label }}</option>
    </select>
    <select v-if="scope==='group'" v-model="refId" class="input mt-2">
      <option v-if="!groups.length" :value="null" disabled>你还没有加入任何课题组</option>
      <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}（ID {{ g.id }}）</option>
    </select>
    <select v-if="scope==='dataset'" v-model="refId" class="input mt-2">
      <option v-if="!datasets.length" :value="null" disabled>你还没有加入任何数据集</option>
      <option v-for="d in datasets" :key="d.id" :value="d.id">{{ d.name }}（ID {{ d.id }}）</option>
    </select>
  </div>
</template>
