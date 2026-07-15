<script setup lang="ts">
// 统一帖子卡片：作者/时间/类型/标题/摘要/关联/标签/范围/点赞·评论数/展开详情/评论回复/编辑删除。
// 研究广场、数据集讨论区、课题组、个人主页共用同一组件与同一份数据。
import { ref } from 'vue'
import api from '../api'
import Icon from './Icon.vue'
import { downloadFile } from '../utils/download'

const props = defineProps<{ post: any; currentUserId?: number }>()
const emit = defineEmits(['changed', 'edit', 'deleted', 'open-dataset', 'open-group'])

const p = ref({ ...props.post })
const expanded = ref(false)
const commentsOpen = ref(false)
const comments = ref<any[]>([])
const cInput = ref(''); const replyTo = ref<any>(null)
const attachments = ref<any[]>([])

// 计数简化：<=99 原样；100-999 → 99+；千级 → x千+；万级 → x万+
function fmtCount(n: number) {
  if (n == null) return 0
  if (n <= 99) return n
  if (n < 1000) return '99+'
  if (n < 10000) return Math.floor(n / 1000) + '千+'
  return Math.floor(n / 10000) + '万+'
}

async function loadDetail() {
  const d = (await api.get(`/posts/${p.value.id}`)).data
  p.value = { ...p.value, ...d }
  attachments.value = d.attachments || []
}
async function toggleExpand() {
  expanded.value = !expanded.value
  if (expanded.value && (p.value.truncated || !attachments.value.length)) await loadDetail()
}
async function like() {
  await api.post(`/posts/${p.value.id}/react`, null, { params: { type: 'like' } })
  p.value.liked = !p.value.liked
  p.value.likes += p.value.liked ? 1 : -1
}
async function follow() {
  const r = (await api.post(`/posts/${p.value.id}/follow`)).data
  p.value.followed = r.followed
}
async function toggleComments() {
  commentsOpen.value = !commentsOpen.value
  if (commentsOpen.value) await loadComments()
}
async function loadComments() {
  comments.value = (await api.get(`/posts/${p.value.id}/comments`)).data
  p.value.comment_count = comments.value.length
}
const topComments = () => comments.value.filter(c => !c.parent_id)
const repliesOf = (id: number) => comments.value.filter(c => c.parent_id === id)
async function sendComment() {
  if (!cInput.value.trim()) return
  await api.post(`/posts/${p.value.id}/comments`, { content: cInput.value.trim(), parent_id: replyTo.value?.id || null })
  cInput.value = ''; replyTo.value = null; await loadComments()
}
async function delComment(c: any) {
  if (!confirm('删除该评论？')) return
  await api.delete(`/comments/${c.id}`); await loadComments()
}
async function likeComment(c: any) {
  await api.post(`/comments/${c.id}/react`, null, { params: { type: 'like' } })
  c.liked = !c.liked; c.likes = (c.likes || 0) + (c.liked ? 1 : -1)
}
async function delPost() {
  if (!confirm('确定删除这条讨论？评论、点赞、附件都会一并删除。')) return
  await api.delete(`/posts/${p.value.id}`); emit('deleted', p.value.id)
}
async function toggleResolved() {
  const next = p.value.status === 'resolved' ? 'open' : 'resolved'
  await api.patch(`/posts/${p.value.id}`, {
    content_zh: p.value.full_content || p.value.content_zh, title: p.value.title,
    post_type: p.value.post_type, status: next, tags: p.value.tags || [],
    scope: p.value.scope, dataset_id: p.value.dataset_id
  })
  p.value.status = next
}
const isMine = () => props.currentUserId && p.value.author_id === props.currentUserId
</script>
<template>
  <div class="card mb-3">
    <!-- 头部 -->
    <div class="flex items-center gap-2 text-sm">
      <div class="w-7 h-7 rounded-full bg-paper overflow-hidden flex items-center justify-center shrink-0">
        <img v-if="p.author_avatar" :src="p.author_avatar" class="w-full h-full object-cover" />
        <Icon v-else name="users" class="ico text-gray-300" style="width:15px;height:15px" />
      </div>
      <router-link :to="`/users/${p.author_id}`" class="text-accent hover:underline font-medium">{{ p.author_name }}</router-link>
      <span class="tag" style="background:#eef2f8;color:#2d4a7c">{{ p.post_type_label }}</span>
      <span v-if="p.status==='resolved'" class="tag" style="background:#e6f4ea;color:#2f7d46">已解决</span>
      <span class="text-gray-400 text-xs">{{ p.created_at }}</span>
      <span class="tag ml-auto">{{ p.scope_label || p.visibility }}</span>
    </div>

    <!-- 标题 + 正文 -->
    <h3 v-if="p.title" class="mt-2 font-medium text-[15px] cursor-pointer hover:text-accent" @click="toggleExpand">{{ p.title }}</h3>
    <p class="mt-1 text-sm text-gray-700 whitespace-pre-line">{{ expanded ? (p.full_content || p.content_zh) : p.content_zh }}</p>
    <button v-if="p.truncated && !expanded" class="text-accent text-xs mt-1" @click="toggleExpand">展开全文 ↓</button>

    <!-- 附件 -->
    <div v-if="expanded && attachments.length" class="mt-2 flex flex-wrap gap-2">
      <button v-for="a in attachments" :key="a.id" class="text-xs text-accent inline-flex items-center gap-1 border border-line rounded px-2 py-1 hover:bg-paper"
        @click="downloadFile(a.url, a.file_name)">
        <Icon name="clip" class="ico" style="width:12px;height:12px" /> {{ a.file_name }}</button>
    </div>

    <!-- 关联 -->
    <div class="mt-2 flex flex-wrap items-center gap-3 text-xs">
      <router-link v-if="p.dataset_slug" :to="`/datasets/${p.dataset_slug}`" class="text-accent hover:underline inline-flex items-center gap-1">
        <Icon name="data" class="ico" style="width:12px;height:12px" />{{ p.dataset_name }}</router-link>
      <router-link v-if="p.group_slug" :to="`/groups/${p.group_slug}`" class="text-accent hover:underline inline-flex items-center gap-1">
        <Icon name="users" class="ico" style="width:12px;height:12px" />{{ p.group_name }}</router-link>
      <span v-for="tag in p.tags" :key="tag" class="tag">{{ tag }}</span>
    </div>

    <!-- 互动栏（社交按钮视觉弱化）-->
    <div class="mt-3 flex items-center gap-4 text-xs text-gray-500">
      <button class="inline-flex items-center gap-1 hover:text-accent2" :class="p.liked ? 'text-accent2' : ''" @click="like">
        <span>{{ p.liked ? '♥' : '♡' }}</span> {{ fmtCount(p.likes) }}</button>
      <button class="inline-flex items-center gap-1 hover:text-accent" @click="toggleComments">
        💬 {{ fmtCount(p.comment_count) }}</button>
      <button class="inline-flex items-center gap-1 hover:text-accent" :class="p.followed ? 'text-accent' : ''" @click="follow">
        {{ p.followed ? '★ 已关注' : '☆ 关注' }}</button>
      <div v-if="isMine()" class="ml-auto flex items-center gap-3">
        <button class="hover:text-accent" @click="toggleResolved">{{ p.status==='resolved' ? '标记未解决' : '标记已解决' }}</button>
        <button class="hover:text-accent" @click="emit('edit', p)">编辑</button>
        <button class="hover:text-accent2" @click="delPost">删除</button>
      </div>
    </div>

    <!-- 评论区 -->
    <div v-if="commentsOpen" class="mt-3 border-t border-line pt-3">
      <div v-for="c in topComments()" :key="c.id" class="mb-2.5">
        <div class="text-sm"><span class="text-accent">{{ c.user_name }}</span>
          <span v-if="c.is_mine" class="tag ml-1" style="background:#eef2f8;color:#2d4a7c">我</span>
          <span class="text-gray-400 text-xs ml-2">{{ c.created_at }}</span></div>
        <p class="text-sm text-gray-700 whitespace-pre-line">{{ c.content }}</p>
        <div class="flex gap-3 text-xs mt-0.5">
          <button class="hover:text-accent2" :class="c.liked ? 'text-accent2' : 'text-gray-500'" @click="likeComment(c)">
            {{ c.liked ? '♥' : '♡' }} {{ c.likes || 0 }}</button>
          <button class="text-gray-500 hover:text-accent" @click="replyTo=c">回复</button>
          <button v-if="c.can_delete" class="text-gray-400 hover:text-accent2" @click="delComment(c)">删除</button>
        </div>
        <div v-for="r in repliesOf(c.id)" :key="r.id" class="ml-5 mt-1.5 pl-3 border-l-2 border-line">
          <div class="text-sm"><span class="text-accent">{{ r.user_name }}</span>
            <span v-if="r.is_mine" class="tag ml-1" style="background:#eef2f8;color:#2d4a7c">我</span>
            <span class="text-gray-400 text-xs ml-2">{{ r.created_at }}</span></div>
          <p class="text-sm text-gray-700 whitespace-pre-line">{{ r.content }}</p>
          <div class="flex gap-3 text-xs mt-0.5">
            <button class="hover:text-accent2" :class="r.liked ? 'text-accent2' : 'text-gray-500'" @click="likeComment(r)">
              {{ r.liked ? '♥' : '♡' }} {{ r.likes || 0 }}</button>
            <button class="text-gray-500 hover:text-accent" @click="replyTo=c">回复</button>
            <button v-if="r.can_delete" class="text-gray-400 hover:text-accent2" @click="delComment(r)">删除</button>
          </div>
        </div>
      </div>
      <p v-if="!topComments().length" class="text-gray-400 text-xs mb-2">还没有评论，来说两句。</p>
      <div v-if="replyTo" class="text-xs text-gray-500 mb-1">回复 @{{ replyTo.user_name }}
        <button class="text-accent2 ml-1" @click="replyTo=null">取消</button></div>
      <div class="flex gap-2">
        <input v-model="cInput" class="input text-sm" placeholder="写评论…" @keyup.enter="sendComment" />
        <button class="btn-primary text-sm" @click="sendComment">发送</button>
      </div>
    </div>
  </div>
</template>
