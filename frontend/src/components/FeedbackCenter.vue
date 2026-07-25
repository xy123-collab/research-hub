<script setup lang="ts">
import { ref } from 'vue'
import api from '../api'

const open = ref(false)
const saving = ref(false)
const doneId = ref<number | null>(null)
const form = ref({
  category: 'feature', title: '', description: '', expected_result: '',
  impact: 'suggestion', page_url: window.location.href
})

function show() {
  doneId.value = null
  form.value.page_url = window.location.href
  open.value = true
}
async function submit() {
  saving.value = true
  try {
    const r = await api.post('/feedback', form.value)
    doneId.value = r.data.id
    form.value = { category: 'feature', title: '', description: '', expected_result: '',
      impact: 'suggestion', page_url: window.location.href }
  } catch (e: any) {
    alert(e.response?.data?.detail || '提交失败，请检查必填项后重试')
  } finally { saving.value = false }
}
defineExpose({ show })
</script>

<template>
  <button class="feedback-fab" title="网站使用问题反馈" @click="show">反馈</button>
  <div v-if="open" class="fixed inset-0 bg-black/40 flex items-center justify-center z-[80] px-4">
    <div class="bg-white rounded-xl border border-line w-full max-w-xl max-h-[85vh] overflow-y-auto p-5">
      <div class="flex justify-between items-start gap-3">
        <div>
          <h2 class="text-lg">网站使用问题反馈</h2>
          <p class="text-xs text-gray-500 mt-1">平台功能、页面显示、账号或权限异常会提交给平台管理员。</p>
        </div>
        <button class="text-gray-400 text-xl" @click="open=false">×</button>
      </div>
      <div v-if="doneId" class="mt-5 rounded-lg bg-green-50 border border-green-200 p-4 text-sm">
        已收到，你的工单编号是 <b>#{{ doneId }}</b>。平台管理员会在后台看到提醒。
        <button class="btn-primary block mt-3" @click="open=false">完成</button>
      </div>
      <form v-else class="mt-4 space-y-3" @submit.prevent="submit">
        <div class="rounded-lg bg-paper p-3 text-xs text-gray-600 leading-5">
          具体数据集或研究项目的研究问题，请联系对应数据集或研究项目管理员；联系邮箱见各自详情页。
        </div>
        <label class="block text-sm">问题类型
          <select v-model="form.category" class="input mt-1" required>
            <option value="feature">网页功能建议</option><option value="display">页面显示或交互问题</option>
            <option value="system">系统故障</option><option value="account">账号与登录问题</option>
            <option value="permission">权限申请或异常</option><option value="upload_download">上传、下载或导入问题</option>
            <option value="privacy">隐私与安全问题</option><option value="other">其他问题</option>
          </select>
        </label>
        <label class="block text-sm">标题<input v-model="form.title" class="input mt-1" maxlength="200" required placeholder="一句话概括问题" /></label>
        <label class="block text-sm">详细描述<textarea v-model="form.description" class="input mt-1 min-h-28" maxlength="5000" required placeholder="请说明操作步骤、出现的现象和时间"></textarea></label>
        <label class="block text-sm">期望结果（选填）<textarea v-model="form.expected_result" class="input mt-1" maxlength="2000"></textarea></label>
        <label class="block text-sm">影响程度
          <select v-model="form.impact" class="input mt-1">
            <option value="suggestion">不影响使用，仅为建议</option><option value="partial">部分功能受影响</option>
            <option value="blocked">无法继续操作</option><option value="security">涉及数据或安全风险</option>
          </select>
        </label>
        <label class="block text-sm">相关页面<input v-model="form.page_url" class="input mt-1" maxlength="800" /></label>
        <div class="flex justify-end gap-2 pt-2">
          <button type="button" class="btn-ghost" @click="open=false">取消</button>
          <button class="btn-primary" :disabled="saving">{{ saving ? '提交中…' : '提交反馈' }}</button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.feedback-fab {
  position: fixed; right: 22px; bottom: 84px; z-index: 59;
  min-width: 52px; height: 34px; padding: 0 11px; border-radius: 9999px;
  background: white; color: var(--accent); border: 1px solid var(--accent);
  font-size: 12px; box-shadow: 0 4px 14px rgba(45, 74, 124, .16);
}
</style>
