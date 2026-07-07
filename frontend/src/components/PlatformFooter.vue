<script setup lang="ts">
import { useI18n } from 'vue-i18n'
defineProps<{ cfg: any }>()
const { locale } = useI18n()
</script>
<template>
  <footer class="border-t border-line mt-10 py-6 text-center text-xs text-gray-500">
    <div class="font-serif text-accent text-sm">
      {{ locale === 'zh' ? cfg.name_zh : cfg.name_en }}
    </div>
    <div class="mt-1">{{ locale === 'zh' ? cfg.slogan_zh : cfg.slogan_en }}</div>
    <div class="mt-1">{{ cfg.footer || '北京大学国家发展研究院 · 智慧科研团队' }} · © {{ new Date().getFullYear() }}</div>
  </footer>
</template>
