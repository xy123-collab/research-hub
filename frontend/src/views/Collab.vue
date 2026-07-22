<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useAuth } from '../stores/auth'
import api from '../api'
import Icon from '../components/Icon.vue'
import ScopeSelector from '../components/ScopeSelector.vue'
import MentionInput from '../components/MentionInput.vue'
import { downloadFile } from '../utils/download'

const auth = useAuth()
const view = ref<'sections' | 'skill' | 'generic'>('sections')
const sections = ref<any[]>([])
const activeSection = ref<any>(null)

onMounted(load)
async function load() { sections.value = (await api.get('/collab/sections')).data }

function openSection(s: any) {
  activeSection.value = s
  if (s.kind === 'skill') { view.value = 'skill'; loadSkills() }
  else view.value = 'generic'
}
function backToSections() { view.value = 'sections'; activeSection.value = null; load() }

// ---- 新建分区（发起其他类型协作）----
const showNewSection = ref(false)
const secForm = ref({ name_zh: '', name_en: '', desc_zh: '' })
async function createSection() {
  if (!secForm.value.name_zh.trim()) { alert('请填写分区名称'); return }
  try {
    await api.post('/collab/sections', secForm.value)
    showNewSection.value = false; secForm.value = { name_zh: '', name_en: '', desc_zh: '' }
    load()
  } catch (e: any) { alert(e.response?.data?.detail || '失败') }
}

// ================= Skill 协作 =================
const skills = ref<any[]>([]); const recos = ref<any[]>([])
async function loadSkills() {
  skills.value = (await api.get('/skills', { params: { section_id: activeSection.value.id } })).data
  try { recos.value = (await api.get('/github-skill-recos')).data } catch {}
}

// 发起 Skill
const showSkill = ref(false)
const skillForm = ref<any>({ name_zh: '', desc_zh: '', body_text: '', github_url: '' })
const skillScope = ref<{ scope: string; scope_ref_ids: number[] }>({ scope: 'public', scope_ref_ids: [] })
const skillFile = ref<File | null>(null)
const SCOPE_LABELS: Record<string, string> = {
  public: '全平台公开', group: '课题组成员可见', dataset: '数据集成员可见', self: '仅自己可见'
}
function openSkillCreate() {
  skillForm.value = { name_zh: '', desc_zh: '', body_text: '', github_url: '' }
  skillScope.value = { scope: 'public', scope_ref_ids: [] }
  skillFile.value = null; showSkill.value = true
}
async function createSkill() {
  if (!skillForm.value.name_zh.trim()) { alert('请填写名称'); return }
  if (!skillForm.value.body_text.trim() && !skillFile.value) { alert('请上传文件或填写文字内容'); return }
  if ((skillScope.value.scope === 'group' || skillScope.value.scope === 'dataset') && !skillScope.value.scope_ref_ids.length) {
    alert('请勾选至少一个课题组/数据集'); return
  }
  const fd = new FormData()
  fd.append('name_zh', skillForm.value.name_zh.trim())
  fd.append('desc_zh', skillForm.value.desc_zh)
  fd.append('body_text', skillForm.value.body_text)
  fd.append('scope', skillScope.value.scope)
  if (skillScope.value.scope_ref_ids.length) fd.append('scope_ref_ids', skillScope.value.scope_ref_ids.join(','))
  fd.append('section_id', String(activeSection.value.id))
  if (skillForm.value.github_url) fd.append('github_url', skillForm.value.github_url)
  if (skillFile.value) fd.append('file', skillFile.value)
  try {
    await api.post('/skills', fd)
    showSkill.value = false; loadSkills()
  } catch (e: any) { alert(e.response?.data?.detail || '发起失败') }
}
function scopeLabel(v: string) { return SCOPE_LABELS[v] || v }

// Skill 详情 + 评论（含评论的评论）
const skillModal = ref<any>(null)
const comments = ref<any[]>([])
const cInput = ref(''); const replyTo = ref<any>(null); const cMentions = ref<any[]>([])
async function openSkill(s: any) {
  skillModal.value = (await api.get(`/skills/${s.id}`)).data
  loadComments()
}
async function loadComments() {
  comments.value = (await api.get(`/skills/${skillModal.value.id}/comments`)).data
}
const topComments = computed(() => comments.value.filter(c => !c.parent_id))
function repliesOf(id: number) { return comments.value.filter(c => c.parent_id === id) }
async function sendComment() {
  if (!cInput.value.trim()) return
  await api.post(`/skills/${skillModal.value.id}/comments`,
    { content: cInput.value.trim(), parent_id: replyTo.value?.id || null,
      mentions: cMentions.value.map(m => ({ target_type: m.target_type, target_id: m.target_id })) })
  cInput.value = ''; cMentions.value = []; replyTo.value = null; loadComments()
}
async function delComment(c: any) {
  if (!confirm('删除该评论？')) return
  await api.delete(`/skills/comments/${c.id}`); loadComments()
}
function downloadSkill(s: any) {
  downloadFile(`/skills/${s.id}/download`, s.file_name || `skill_${s.id}`)
}
</script>
<template>
  <!-- ========== 分区总览 ========== -->
  <div v-if="view==='sections'">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h1 class="text-2xl">其他协作</h1>
        <p class="text-sm text-gray-500 mt-1">按类型分区协作。点进分区参与，或发起新的协作类型。</p>
      </div>
      <button class="btn-primary" @click="showNewSection=true">＋发起其他类型协作</button>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <button v-for="s in sections" :key="s.id" class="card text-left hover:shadow-md transition"
        @click="openSection(s)">
        <h3 class="flex items-center gap-2">
          <Icon :name="s.kind==='skill'?'puzzle':'users'" class="ico text-accent" /> {{ s.name_zh }}
        </h3>
        <p class="text-sm text-gray-500 mt-1">{{ s.desc_zh || '协作分区' }}</p>
        <div class="text-xs text-gray-400 mt-2">{{ s.item_count }} 项 · {{ s.kind==='skill'?'内置':'自定义' }}</div>
      </button>
    </div>

    <div v-if="showNewSection" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg max-w-md w-full p-6 m-4">
        <h3 class="text-lg mb-3">发起其他类型协作（新建分区）</h3>
        <input v-model="secForm.name_zh" class="input mb-2" placeholder="分区名称（如：数据清洗协作 / 文献共读）" />
        <input v-model="secForm.name_en" class="input mb-2" placeholder="英文名（可选）" />
        <textarea v-model="secForm.desc_zh" class="input mb-3" placeholder="简介（可选）"></textarea>
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showNewSection=false">取消</button>
          <button class="btn-primary" @click="createSection">创建分区</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ========== Skill 协作分区 ========== -->
  <div v-else-if="view==='skill'">
    <button class="text-accent text-sm mb-3 hover:underline" @click="backToSections">← 返回分区</button>
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl flex items-center gap-2"><Icon name="puzzle" class="ico text-accent" /> {{ activeSection.name_zh }}</h1>
      <button class="btn-primary" @click="openSkillCreate">＋发起 Skill</button>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div v-for="s in skills" :key="s.id" class="card">
        <h3 class="flex items-center gap-2 cursor-pointer" @click="openSkill(s)">
          <Icon name="puzzle" class="ico text-accent" /> {{ s.name_zh }}
        </h3>
        <p class="text-sm text-gray-500 mt-1">{{ s.desc_zh }}</p>
        <div class="flex items-center gap-2 mt-2 text-xs text-gray-400">
          <span class="tag">{{ scopeLabel(s.scope) }}</span>
          <span>{{ s.founder_name }}</span>
        </div>
        <div class="flex items-center gap-3 mt-3 text-xs">
          <button class="text-accent hover:underline" @click="openSkill(s)">评论（{{ s.comment_count }}）</button>
          <button v-if="s.has_file" class="text-accent hover:underline" @click="downloadSkill(s)">下载</button>
          <a v-if="s.github_url" :href="s.github_url" target="_blank" class="text-accent">GitHub ↗</a>
        </div>
      </div>
      <p v-if="!skills.length" class="text-gray-400 text-sm">暂无 Skill，点右上角发起一个。</p>
    </div>

    <template v-if="recos.length">
      <h2 class="text-lg mt-8 mb-3">GitHub 推荐 Skill</h2>
      <ul class="text-sm space-y-1">
        <li v-for="r in recos" :key="r.id"><a :href="r.github_url" target="_blank" class="text-accent">{{ r.name }} ↗</a> · {{ r.note }}</li>
      </ul>
    </template>

    <!-- 发起 Skill 弹窗 -->
    <div v-if="showSkill" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg max-w-lg w-full p-6 m-4 max-h-[88vh] overflow-y-auto">
        <h3 class="text-lg mb-3">发起 Skill</h3>
        <input v-model="skillForm.name_zh" class="input mb-2" placeholder="名称 *" />
        <input v-model="skillForm.desc_zh" class="input mb-2" placeholder="一句话简介" />
        <label class="label-cap">内容（文字，二选一或都填）</label>
        <textarea v-model="skillForm.body_text" rows="4" class="input mb-2" placeholder="粘贴脚本 / 流程 / 提示词等文字内容"></textarea>
        <label class="label-cap">上传文件（可选）</label>
        <input type="file" class="text-xs mb-3 block" @change="(e:any)=>skillFile=e.target.files[0]" />
        <div class="mb-3"><ScopeSelector v-model="skillScope" /></div>
        <input v-model="skillForm.github_url" class="input mb-3" placeholder="GitHub 链接（可选）" />
        <div class="flex justify-end gap-2">
          <button class="btn-ghost" @click="showSkill=false">取消</button>
          <button class="btn-primary" @click="createSkill">发起</button>
        </div>
      </div>
    </div>

    <!-- Skill 详情 + 评论 -->
    <div v-if="skillModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-lg max-w-2xl w-full p-6 m-4 max-h-[88vh] overflow-y-auto">
        <div class="flex items-center justify-between">
          <h3 class="text-lg">{{ skillModal.name_zh }}</h3>
          <button @click="skillModal=null" class="text-gray-400"><Icon name="close" class="ico" style="width:18px;height:18px" /></button>
        </div>
        <div class="flex items-center gap-2 mt-1 text-xs text-gray-400">
          <span class="tag">{{ scopeLabel(skillModal.scope) }}</span>
          <span>{{ skillModal.founder_name }}</span>
        </div>
        <p v-if="skillModal.desc_zh" class="text-sm text-gray-600 mt-2">{{ skillModal.desc_zh }}</p>
        <pre v-if="skillModal.body_text" class="bg-paper rounded p-3 text-xs whitespace-pre-wrap mt-2 max-h-60 overflow-y-auto">{{ skillModal.body_text }}</pre>
        <div class="flex items-center gap-3 mt-3 text-sm">
          <button v-if="skillModal.has_file" class="btn-ghost text-xs" @click="downloadSkill(skillModal)">
            <Icon name="clip" class="ico" style="width:12px;height:12px" /> 下载 {{ skillModal.file_name }}</button>
        </div>

        <!-- 评论区（含评论的评论）-->
        <div class="mt-5 border-t border-line pt-4">
          <div class="label-cap mb-2">评论</div>
          <div v-for="c in topComments" :key="c.id" class="mb-3">
            <div class="text-sm"><span class="text-accent">{{ c.user_name }}</span>
              <span class="text-gray-400 text-xs ml-2">{{ (c.created_at||'').slice(0,16).replace('T',' ') }}</span></div>
            <p class="text-sm text-gray-700">{{ c.content }}</p>
            <div class="flex gap-2 text-xs mt-0.5">
              <button class="text-gray-500 hover:text-accent" @click="replyTo=c">回复</button>
              <button class="text-gray-400 hover:text-accent2" @click="delComment(c)">删除</button>
            </div>
            <!-- 回复（评论的评论）-->
            <div v-for="r in repliesOf(c.id)" :key="r.id" class="ml-5 mt-2 pl-3 border-l-2 border-line">
              <div class="text-sm"><span class="text-accent">{{ r.user_name }}</span>
                <span class="text-gray-400 text-xs ml-2">{{ (r.created_at||'').slice(0,16).replace('T',' ') }}</span></div>
              <p class="text-sm text-gray-700">{{ r.content }}</p>
              <button class="text-gray-400 hover:text-accent2 text-xs" @click="delComment(r)">删除</button>
            </div>
          </div>
          <p v-if="!topComments.length" class="text-gray-400 text-sm mb-2">还没有评论。</p>

          <div class="mt-2">
            <div v-if="replyTo" class="text-xs text-gray-500 mb-1">回复 @{{ replyTo.user_name }}
              <button class="text-accent2 ml-1" @click="replyTo=null">取消</button></div>
            <div class="flex gap-2">
              <div class="flex-1"><MentionInput v-model="cInput" v-model:mentions="cMentions" placeholder="写下你的评论…（输入 @ 提及成员）" @enter="sendComment" /></div>
              <button class="btn-primary text-sm shrink-0" @click="sendComment">发送</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ========== 通用分区（占位）========== -->
  <div v-else>
    <button class="text-accent text-sm mb-3 hover:underline" @click="backToSections">← 返回分区</button>
    <h1 class="text-2xl flex items-center gap-2"><Icon name="users" class="ico text-accent" /> {{ activeSection.name_zh }}</h1>
    <p class="text-sm text-gray-500 mt-2">{{ activeSection.desc_zh }}</p>
    <div class="card mt-4 text-center text-gray-400 text-sm py-10">
      该协作分区已创建。发起具体协作项的功能可按需接入（当前 Skill 分区已支持完整发起/评论/下载流程）。
    </div>
  </div>
</template>
