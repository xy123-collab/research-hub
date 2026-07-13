<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuth } from './stores/auth'
import api from './api'
import PlatformFooter from './components/PlatformFooter.vue'
import NotificationCenter from './components/NotificationCenter.vue'

const auth = useAuth()
const route = useRoute()
const { locale, t } = useI18n()
const cfg = ref<any>({ name_zh: '科研数据共享平台', name_en: 'Research Hub' })

const showNav = computed(() => route.path !== '/login')

onMounted(async () => {
  await auth.fetchMe()
  try { cfg.value = (await api.get('/config')).data } catch {}
})

function toggleLang() {
  locale.value = locale.value === 'zh' ? 'en' : 'zh'
  localStorage.setItem('lang', locale.value)
}
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <header v-if="showNav" class="border-b border-line bg-white/80 backdrop-blur sticky top-0 z-20">
      <div class="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <div class="flex items-center gap-6">
          <router-link to="/" class="font-serif text-lg font-semibold text-accent">
            {{ locale === 'zh' ? cfg.name_zh : cfg.name_en }}
          </router-link>
          <nav class="flex gap-4 text-sm">
            <router-link to="/" class="hover:text-accent">{{ t('nav.home') }}</router-link>
            <router-link to="/groups" class="hover:text-accent">{{ t('nav.groups') }}</router-link>
            <router-link to="/feed" class="hover:text-accent">{{ t('nav.feed') }}</router-link>
            <router-link to="/me" class="hover:text-accent">{{ t('nav.profile') }}</router-link>
            <router-link to="/skills" class="hover:text-accent">{{ t('nav.skills') }}</router-link>
            <router-link to="/admin" class="hover:text-accent">{{ t('nav.admin') }}</router-link>
          </nav>
        </div>
        <div class="flex items-center gap-3 text-sm">
          <button @click="toggleLang" class="btn-ghost">{{ locale === 'zh' ? 'EN' : '中文' }}</button>
          <span v-if="auth.user" class="text-gray-500">{{ auth.user.display_name }}</span>
          <button v-if="auth.user" @click="auth.logout()" class="hover:text-accent2">{{ t('nav.logout') }}</button>
        </div>
      </div>
    </header>

    <main class="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
      <router-view />
    </main>

    <PlatformFooter :cfg="cfg" />

    <!-- 集中消息入口：登录后显示右下角悬浮铃铛 -->
    <NotificationCenter v-if="auth.user && showNav" />
  </div>
</template>
