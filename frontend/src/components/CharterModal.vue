<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import api from '../api'

const props = defineProps<{ scope: string; refId: number }>()
const { t } = useI18n()
const charter = ref<any>(null)
const show = ref(false)

watch(() => [props.scope, props.refId], load, { immediate: true })

async function load() {
  if (!props.refId) return
  const { data } = await api.get('/charters', { params: { scope: props.scope, ref: props.refId } })
  if (data.charter && !data.acked) { charter.value = data.charter; show.value = true }
}
async function agree() {
  await api.post(`/charters/${charter.value.id}/ack`)
  show.value = false
}
</script>
<template>
  <div v-if="show" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg max-w-lg w-full p-6 m-4">
      <h3 class="text-lg mb-3">📜 {{ scope === 'group' ? '课题组公约' : '数据集公约' }}
        <span class="tag ml-2">v{{ charter.version }}</span></h3>
      <pre class="whitespace-pre-wrap bg-paper text-ink border border-line max-h-64 overflow-y-auto">{{ charter.body_zh }}</pre>
      <div class="mt-4 flex justify-end">
        <button class="btn-primary" @click="agree">{{ t('common.agree') }}</button>
      </div>
    </div>
  </div>
</template>
