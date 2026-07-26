<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import api from '../api'

const props = defineProps<{ src: string }>()
const resolved = ref('')
let objectUrl = ''
let generation = 0

function clearObjectUrl() {
  if (objectUrl) URL.revokeObjectURL(objectUrl)
  objectUrl = ''
}

watch(() => props.src, async (src) => {
  const current = ++generation
  clearObjectUrl()
  resolved.value = ''
  if (!src) return
  if (!src.startsWith('/api/')) {
    resolved.value = src
    return
  }
  try {
    const path = src.slice('/api'.length)
    const { data } = await api.get(path, { responseType: 'blob' })
    if (current !== generation) return
    objectUrl = URL.createObjectURL(data)
    resolved.value = objectUrl
  } catch {
    if (current === generation) resolved.value = ''
  }
}, { immediate: true })

onBeforeUnmount(() => {
  generation += 1
  clearObjectUrl()
})
</script>

<template>
  <img v-if="resolved" :src="resolved" />
</template>
