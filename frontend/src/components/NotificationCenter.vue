<script setup lang="ts">
// 集中消息入口：右下角悬浮铃铛 + 红点角标 + 消息面板。
// 聚合当前用户在各课题组/数据集作为管理员的待办（加入审批/下载审批/勘误终审/归属审批）
// 以及与我相关的状态变更。轮询 /notifications。
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import Icon from './Icon.vue'

const router = useRouter()
const open = ref(false)
const groups = ref<any[]>([])
const badgeCount = ref(0)

let timer: any = null

async function load() {
  try {
    const r = (await api.get('/notifications')).data
    groups.value = r.groups || []
    badgeCount.value = r.badge_count || 0
  } catch { /* 未登录时静默 */ }
}

async function markAllRead() {
  try { await api.post('/notifications/mark-read'); await load() } catch {}
}

function go(it: any) {
  open.value = false
  if (it.link) router.push(it.link)
}

const badge = computed(() => badgeCount.value > 99 ? '99+' : String(badgeCount.value))
const hasAny = computed(() => groups.value.some(g => g.items?.length))

onMounted(() => {
  load()
  timer = setInterval(load, 60000)
})
onUnmounted(() => timer && clearInterval(timer))
defineExpose({ load })
</script>

<template>
  <div>
    <!-- 悬浮铃铛（未读用红色圆形数字角标）-->
    <button class="notif-fab" @click="open = !open" :title="'消息 (' + badgeCount + ')'">
      <Icon name="bell" class="ico" style="width:22px;height:22px" />
      <span v-if="badgeCount > 0" class="notif-badge">{{ badge }}</span>
    </button>

    <!-- 面板 -->
    <div v-if="open" class="notif-overlay" @click.self="open = false">
      <div class="notif-panel">
        <div class="notif-head">
          <span class="font-medium">消息中心</span>
          <div class="flex items-center gap-2">
            <button class="text-xs text-gray-500 hover:text-accent" @click="markAllRead">全部已读</button>
            <button class="text-xs text-gray-500 hover:text-accent" @click="load">刷新</button>
            <button class="text-gray-400" @click="open = false">
              <Icon name="close" class="ico" style="width:16px;height:16px" />
            </button>
          </div>
        </div>

        <div class="notif-body">
          <p v-if="!hasAny" class="p-6 text-center text-sm text-gray-400">
            暂无消息。申请审批、被评论、被设为管理员、被拉入工作台、新数据/代码发布等都会在这里分类提醒你。
          </p>

          <template v-for="g in groups" :key="g.key">
            <div class="notif-section" :style="{ color: g.color }">
              {{ g.name }}（{{ g.count }}）
              <span v-if="g.unread" class="notif-unread-pill">{{ g.unread > 99 ? '99+' : g.unread }} 未读</span>
            </div>
            <button v-for="(it, i) in g.items" :key="g.key + i" class="notif-item"
              :class="{ 'notif-item-unread': it.unread }" @click="go(it)">
              <span class="dot mt-1.5" :style="{ background: g.color }"></span>
              <span class="min-w-0 flex-1 text-left">
                <span class="block text-sm text-gray-800">{{ it.title }}
                  <span v-if="it.unread" class="notif-new">新</span>
                  <span v-if="it.at" class="text-[11px] text-gray-400 font-normal ml-1">{{ it.at }}</span></span>
                <span class="block text-xs text-gray-500 truncate">{{ it.subtitle }}</span>
              </span>
              <span v-if="it.level === 'action'" class="notif-cta">去处理</span>
            </button>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.notif-fab {
  position: fixed; right: 22px; bottom: 22px; z-index: 60;
  width: 52px; height: 52px; border-radius: 9999px;
  background: var(--accent); color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6px 20px rgba(45, 74, 124, .35);
  transition: transform .15s, box-shadow .15s;
}
.notif-fab:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(45, 74, 124, .45); }
.notif-badge {
  position: absolute; top: -3px; right: -3px; min-width: 20px; height: 20px;
  padding: 0 5px; border-radius: 9999px; background: #c0392b; color: #fff;
  font-size: 11px; line-height: 20px; text-align: center; border: 2px solid #fff;
}
.notif-overlay { position: fixed; inset: 0; z-index: 61; }
.notif-panel {
  position: fixed; right: 22px; bottom: 84px; width: 360px; max-width: calc(100vw - 32px);
  max-height: 70vh; background: #fff; border: 1px solid var(--line, #e5e7eb);
  border-radius: 14px; box-shadow: 0 12px 40px rgba(0, 0, 0, .18);
  display: flex; flex-direction: column; overflow: hidden;
}
.notif-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid var(--line, #e5e7eb);
}
.notif-body { overflow-y: auto; }
.notif-section {
  padding: 8px 14px 4px; font-size: 11px; letter-spacing: .04em;
  color: #9aa0a6; background: #fafafa;
}
.notif-item {
  width: 100%; display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 14px; border-top: 1px solid #f1f2f4;
}
.notif-item:hover { background: #f7f8fa; }
.notif-cta {
  font-size: 11px; color: var(--accent); border: 1px solid var(--accent);
  border-radius: 6px; padding: 2px 6px; white-space: nowrap; align-self: center;
}
.notif-item-unread { background: #f5f8ff; }
.notif-item-unread:hover { background: #eef3fe; }
.notif-unread-pill {
  float: right; background: #c0392b; color: #fff; border-radius: 9999px;
  font-size: 10px; padding: 0 6px; line-height: 16px;
}
.notif-new {
  display: inline-block; background: #c0392b; color: #fff; font-size: 10px;
  border-radius: 4px; padding: 0 4px; margin-left: 4px; vertical-align: middle;
}
</style>
