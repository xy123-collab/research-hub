<script setup lang="ts">
// 历史下载弹窗：数据集页与个人主页共用同一个入口/组件，展示跨数据集及其它位置的
// 下载记录（下载时间 + 文件名 + 位置）。传 datasetId 时默认只看该数据集，可切到全部。
import { ref, watch } from 'vue'
import api from '../api'
import Icon from './Icon.vue'

const props = defineProps<{ open: boolean; datasetId?: number; datasetName?: string }>()
const emit = defineEmits(['close'])

const items = ref<any[]>([])
const loading = ref(false)
const onlyThis = ref(true)   // 数据集页默认只看本数据集

async function load() {
  loading.value = true
  try {
    const params: any = {}
    if (props.datasetId && onlyThis.value) params.dataset_id = props.datasetId
    items.value = (await api.get('/me/downloads', { params })).data.items || []
  } catch { items.value = [] }
  finally { loading.value = false }
}
watch(() => props.open, v => { if (v) { onlyThis.value = !!props.datasetId; load() } })
watch(onlyThis, () => { if (props.open) load() })
</script>
<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" @click.self="emit('close')">
    <div class="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
      <div class="flex items-center gap-2 px-5 py-3 border-b border-line">
        <Icon name="data" class="ico text-accent" style="width:16px;height:16px" />
        <h3 class="text-base font-medium">历史下载</h3>
        <label v-if="datasetId" class="text-xs text-gray-500 ml-3 flex items-center gap-1">
          <input type="checkbox" v-model="onlyThis" /> 仅看「{{ datasetName || '本数据集' }}」</label>
        <button class="ml-auto text-gray-400 hover:text-accent2" @click="emit('close')">✕</button>
      </div>
      <div class="overflow-auto p-4">
        <p v-if="loading" class="text-gray-400 text-sm">加载中…</p>
        <p v-else-if="!items.length" class="text-gray-400 text-sm py-8 text-center">还没有下载记录。</p>
        <table v-else class="w-full text-sm">
          <thead>
            <tr class="text-left text-gray-400 border-b border-line">
              <th class="py-2 pr-2">下载时间</th><th class="pr-2">文件名</th>
              <th class="pr-2">位置</th><th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in items" :key="r.id" class="border-b border-line/60 hover:bg-paper">
              <td class="py-2 pr-2 text-gray-500 whitespace-nowrap">{{ r.downloaded_at }}</td>
              <td class="pr-2">
                <a v-if="r.link" :href="'#' + r.link.replace('/#','')" class="text-accent hover:underline break-all">{{ r.file_name }}</a>
                <span v-else class="break-all">{{ r.file_name }}</span>
              </td>
              <td class="pr-2">
                <span class="tag" style="background:#eef2f8;color:#2d4a7c">{{ r.source_label }}</span>
                <span class="ml-1 text-gray-600">{{ r.location }}</span>
              </td>
              <td class="text-gray-500">{{ r.detail }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
