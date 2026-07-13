<script setup lang="ts">
// 统一的极简线性图标：细描边、随文字色。用法 <Icon name="chart" />
const props = defineProps<{ name: string }>()
const P: Record<string, string> = {
  correct: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 12l3 3 5-6"/>',
  chart: '<line x1="3" y1="20" x2="21" y2="20"/><rect x="5" y="11" width="3" height="7"/><rect x="10.5" y="6" width="3" height="12"/><rect x="16" y="13" width="3" height="5"/>',
  verify: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>',
  code: '<path d="M8 8l-4 4 4 4"/><path d="M16 8l4 4-4 4"/>',
  layers: '<path d="M12 3l8 4-8 4-8-4 8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 17l8 4 8-4"/>',
  bulb: '<path d="M9 18h6"/><path d="M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10c.6.6 1 1.5 1 2h6c0-.5.4-1.4 1-2a6 6 0 0 0-4-10z"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>',
  publish: '<path d="M12 15V3"/><path d="M7 8l5-5 5 5"/><path d="M5 21h14"/>',
  clip: '<path d="M21 12l-9 9a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8"/>',
  doc: '<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M11 11.5h1.2V17"/>',
  users: '<circle cx="9" cy="8" r="3"/><path d="M3.5 20c0-3 2.7-5 5.5-5s5.5 2 5.5 5"/><path d="M16 5.5a3 3 0 0 1 0 6"/><path d="M20.5 20c0-2.4-1.7-3.9-3.5-4.4"/>',
  puzzle: '<path d="M9 4h6v3a2 2 0 1 0 4 0V4h1v6h-3a2 2 0 1 0 0 4h3v6h-6v-3a2 2 0 1 0-4 0v3H4v-6h3a2 2 0 1 0 0-4H4V4h5z"/>',
  data: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
}
const path = () => P[props.name] || P.data
</script>
<template>
  <svg class="ico" viewBox="0 0 24 24" v-html="path()"></svg>
</template>
