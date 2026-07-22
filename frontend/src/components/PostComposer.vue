<script setup lang="ts">
// 统一「发布讨论」集成入口：研究讨论区 / 数据集讨论区 / 课题组 / 个人主页 共用。
// 只改变默认关联对象（context），字段与规则一致。支持编辑已有帖子。
import { ref, onMounted } from 'vue'
import api from '../api'
import Icon from './Icon.vue'
import ScopeSelector from './ScopeSelector.vue'

const props = defineProps<{
  context?: { datasetId?: number; datasetName?: string; groupId?: number; groupName?: string }
  edit?: any | null
}>()
const emit = defineEmits(['close', 'saved'])

const TYPES = [
  { v: 'question', label: '研究问题' }, { v: 'data', label: '数据问题' },
  { v: 'method', label: '方法讨论' }, { v: 'collab', label: '合作招募' },
  { v: 'discussion', label: '自由讨论' },
]

const form = ref<any>({ title: '', content_zh: '', post_type: 'discussion', tags: '' })
const scope = ref<{ scope: string; scope_ref_ids: number[] }>({ scope: 'public', scope_ref_ids: [] })
const saving = ref(false)

// 关联数据集（自动匹配）
const dsQuery = ref(''); const dsResults = ref<any[]>([]); const dsLinked = ref<any>(null)
let dsTimer: any = null
function onDsInput() {
  dsLinked.value = null; clearTimeout(dsTimer)
  dsTimer = setTimeout(async () => {
    const q = dsQuery.value.trim(); if (!q) { dsResults.value = []; return }
    try { dsResults.value = (await api.get('/datasets/search', { params: { q } })).data } catch { dsResults.value = [] }
  }, 250)
}
function pickDs(d: any) { dsLinked.value = d; dsQuery.value = d.name; dsResults.value = [] }
function clearDs() { dsLinked.value = null; dsQuery.value = ''; dsResults.value = [] }

// 附件（发布后上传，可下载）
const files = ref<File[]>([])
function pickFiles(e: any) { files.value = Array.from(e.target.files || []) }

onMounted(() => {
  if (props.edit) {
    form.value = {
      title: props.edit.title || '', content_zh: props.edit.full_content || props.edit.content_zh || '',
      post_type: props.edit.post_type || 'discussion', tags: (props.edit.tags || []).join(', ')
    }
    scope.value = { scope: props.edit.scope || 'public', scope_ref_ids: [] }
    if (props.edit.dataset_id) dsLinked.value = { id: props.edit.dataset_id, name: props.edit.dataset_name }
  } else if (props.context?.datasetId) {
    // 数据集内发布：默认关联当前数据集
    dsLinked.value = { id: props.context.datasetId, name: props.context.datasetName }
    dsQuery.value = props.context.datasetName || ''
  }
})

async function submit() {
  if (!form.value.title.trim() && !form.value.content_zh.trim()) { alert('标题或正文至少填一项'); return }
  if ((scope.value.scope === 'group' || scope.value.scope === 'dataset') && !scope.value.scope_ref_ids.length) {
    alert('请勾选至少一个课题组/数据集作为可见范围'); return
  }
  saving.value = true
  try {
    const payload: any = {
      title: form.value.title.trim() || null,
      content_zh: form.value.content_zh.trim(),
      post_type: form.value.post_type,
      tags: form.value.tags ? form.value.tags.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean) : [],
      scope: scope.value.scope, scope_ref_ids: scope.value.scope_ref_ids,
      dataset_id: dsLinked.value?.id || props.context?.datasetId || null,
      group_id: props.context?.groupId || null,
    }
    let pid = props.edit?.id
    if (props.edit) await api.patch(`/posts/${pid}`, payload)
    else pid = (await api.post('/posts', payload)).data.id
    // 上传附件
    for (const f of files.value) {
      const fd = new FormData(); fd.append('file', f)
      try { await api.post(`/posts/${pid}/attachments`, fd) } catch (e: any) { alert('附件上传失败：' + (e.response?.data?.detail || f.name)) }
    }
    emit('saved'); emit('close')
  } catch (e: any) { alert(e.response?.data?.detail || '发布失败') }
  finally { saving.value = false }
}
</script>
<template>
  <div class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
    <div class="bg-white rounded-lg max-w-lg w-full p-6 m-4 max-h-[90vh] overflow-y-auto">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-lg">{{ edit ? '编辑讨论' : '发布讨论' }}</h3>
        <button class="text-gray-400" @click="emit('close')"><Icon name="close" class="ico" style="width:18px;height:18px" /></button>
      </div>

      <label class="label-cap">讨论类型</label>
      <div class="flex flex-wrap gap-1.5 mb-3">
        <button v-for="tp in TYPES" :key="tp.v" type="button"
          :class="['text-xs px-2.5 py-1 rounded-full border', form.post_type===tp.v ? 'bg-accent text-white border-accent' : 'border-line text-gray-600']"
          @click="form.post_type=tp.v">{{ tp.label }}</button>
      </div>

      <label class="label-cap">标题</label>
      <input v-model="form.title" class="input mb-2" placeholder="一句话概括你的研究问题 / 讨论主题" />

      <label class="label-cap">正文</label>
      <textarea v-model="form.content_zh" rows="4" class="input mb-2" placeholder="展开描述背景、你已经尝试了什么、想讨论的点…"></textarea>

      <div class="grid md:grid-cols-2 gap-3">
        <div>
          <ScopeSelector v-model="scope" />
        </div>
        <div>
          <label class="label-cap">关联数据集（可选）</label>
          <div class="relative">
            <div v-if="dsLinked" class="flex items-center gap-2 text-sm">
              <span class="tag border-accent text-accent">🔗 {{ dsLinked.name }}（ID {{ dsLinked.id }}）</span>
              <button type="button" class="text-accent2 text-xs" @click="clearDs">取消关联</button>
            </div>
            <template v-else>
              <input v-model="dsQuery" class="input" placeholder="输入关键词自动匹配" @input="onDsInput" />
              <div v-if="dsResults.length" class="absolute z-10 left-0 right-0 bg-white border border-line rounded mt-1 max-h-40 overflow-y-auto shadow">
                <button v-for="d in dsResults" :key="d.id" type="button" class="w-full text-left px-3 py-1.5 text-sm hover:bg-paper"
                  @click="pickDs(d)">{{ d.name }} <span class="text-gray-400 text-xs">ID {{ d.id }}</span></button>
              </div>
            </template>
          </div>
          <p v-if="context?.groupName" class="text-[11px] text-gray-400 mt-2">默认关联当前课题组：{{ context.groupName }}</p>

          <label class="label-cap mt-2">标签（逗号分隔）</label>
          <input v-model="form.tags" class="input" placeholder="如 COD, 因果推断" />
        </div>
      </div>

      <label class="label-cap mt-3">附件 / 相关文件（可选，发布后可下载）</label>
      <input type="file" multiple class="text-xs" @change="pickFiles" />
      <p v-if="files.length" class="text-[11px] text-gray-500 mt-1">已选 {{ files.length }} 个文件</p>

      <div class="flex justify-end gap-2 mt-4">
        <button class="btn-ghost" @click="emit('close')">取消</button>
        <button class="btn-primary" :disabled="saving" @click="submit">{{ saving ? '发布中…' : (edit ? '保存修改' : '发布') }}</button>
      </div>
    </div>
  </div>
</template>
