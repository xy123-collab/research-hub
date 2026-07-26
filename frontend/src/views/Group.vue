<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { downloadFile } from '../utils/download'
import { useAuth } from '../stores/auth'
import PostCard from '../components/PostCard.vue'
import PostComposer from '../components/PostComposer.vue'
import { formatChinaDate, formatChinaDateTime } from '../utils/time'

const route = useRoute(); const router = useRouter()
const auth = useAuth()
const g = ref<any>(null); const tab = ref('overview')
const tabs = [['overview','概览'],['members','成员'],['datasets','数据集'],['links','Overleaf / 链接'],
  ['timeline','时间线'],['files','文件'],['discussion','内部讨论']]
const slug = () => route.params.slug as string
const showEdit = ref(false); const editForm = ref<any>({})
const showDataset = ref(false); const dsForm = ref({ name_zh:'', desc_zh:'' })
const inviteQ = ref(''); const inviteResults = ref<any[]>([])
const linkForm = ref({ title:'', url:'' })
const timelineForm = ref({ category:'progress', title:'', body:'' }); const timelineFile = ref<File|null>(null)
const projectFile = ref<File|null>(null)
const projectPosts = ref<any[]>([]); const composerOpen = ref(false); const editingPost = ref<any>(null)

onMounted(load); watch(() => route.params.slug, load)
async function load() {
  try {
    g.value = (await api.get(`/groups/${slug()}`)).data
    projectPosts.value = (await api.get('/posts', { params:{ group_id:g.value.id } })).data
  }
  catch (e: any) { alert(e.response?.data?.detail || '无法访问该研究项目'); router.push('/groups') }
}
function roleLabel(m: any) { return m.is_lead ? 'Owner' : m.is_admin ? 'Admin' : 'Member' }
function openEdit() {
  editForm.value = { name_zh:g.value.name_zh, name_en:g.value.name_en,
    desc_zh:g.value.desc_zh, desc_en:g.value.desc_en, icon:g.value.icon, discoverable:false }
  showEdit.value = true
}
async function saveEdit() { await api.patch(`/groups/${slug()}`, editForm.value); showEdit.value=false; load() }
async function deleteProject() {
  if (!confirm('删除研究项目后将永久下架，且必须先处理内部数据集。是否继续？')) return
  const confirmation = prompt(`请输入完整项目名称确认：${g.value.name_zh}`)
  if (confirmation === null) return
  try { await api.delete(`/groups/${slug()}`, { data:{ confirmation } }); router.push('/groups') }
  catch (e:any) { alert(e.response?.data?.detail || '删除失败') }
}
async function searchUsers() {
  inviteResults.value = (await api.get('/users/search', { params:{ q:inviteQ.value, limit:20 } })).data
    .filter((u:any) => !(g.value.members || []).some((m:any) => m.user_id === u.id))
}
async function invite(uid:number) {
  try { await api.post(`/groups/${slug()}/invite/${uid}`); inviteQ.value=''; inviteResults.value=[]; load() }
  catch(e:any){ alert(e.response?.data?.detail || '邀请失败') }
}
async function addAdmin(uid:number){ await api.post(`/groups/${slug()}/admins/${uid}`); load() }
async function removeAdmin(uid:number){ await api.delete(`/groups/${slug()}/admins/${uid}`); load() }
async function removeMember(uid:number){ if(confirm('确认移除该成员？')){ await api.delete(`/groups/${slug()}/members/${uid}`); load() } }
async function transferLead(uid:number){ if(confirm('确认移交 Owner？你将变为 Admin。')){ await api.post(`/groups/${slug()}/transfer-lead/${uid}`); load() } }
async function createDataset(){
  if(!dsForm.value.name_zh.trim()) return alert('请填写数据集名称')
  try { const r=await api.post(`/groups/${slug()}/datasets`,dsForm.value); showDataset.value=false; router.push(`/datasets/${r.data.slug}`) }
  catch(e:any){ alert(e.response?.data?.detail || '创建失败') }
}
async function addLink(){
  const fd=new FormData(); fd.append('title',linkForm.value.title); fd.append('url',linkForm.value.url)
  try { await api.post(`/groups/${slug()}/links`,fd); linkForm.value={title:'',url:''}; load() }
  catch(e:any){ alert(e.response?.data?.detail || '保存失败') }
}
async function editLink(x:any){
  const title=prompt('链接标题',x.title); if(title===null)return
  const url=prompt('链接地址',x.url); if(url===null)return
  await api.patch(`/groups/${slug()}/links/${x.id}`,{title,url}); load()
}
async function delLink(id:number){ if(confirm('删除该链接？')){await api.delete(`/groups/${slug()}/links/${id}`);load()} }
async function addTimeline(){
  const fd=new FormData(); Object.entries(timelineForm.value).forEach(([k,v])=>fd.append(k,v))
  if(timelineFile.value)fd.append('file',timelineFile.value)
  try { await api.post(`/groups/${slug()}/timeline`,fd); timelineForm.value={category:'progress',title:'',body:''};timelineFile.value=null;load() }
  catch(e:any){alert(e.response?.data?.detail || '记录失败')}
}
async function uploadFile(){
  if(!projectFile.value)return alert('请选择文件')
  const fd=new FormData();fd.append('file',projectFile.value)
  try{await api.post(`/groups/${slug()}/files`,fd);projectFile.value=null;load()}catch(e:any){alert(e.response?.data?.detail||'上传失败')}
}
async function delFile(id:number){if(confirm('删除该文件？')){await api.delete(`/groups/${slug()}/files/${id}`);load()}}
function newDiscussion(){ editingPost.value=null; composerOpen.value=true }
function editDiscussion(p:any){ editingPost.value=p; composerOpen.value=true }
function postDeleted(id:number){ projectPosts.value=projectPosts.value.filter((p:any)=>p.id!==id) }
const canInvite = computed(()=>!!g.value?.is_admin)
const categoryName:Record<string,string>={progress:'重大进展',discussion:'讨论记录',chart:'图表结果',todo:'待办',other:'其他'}
</script>

<template>
  <div v-if="g">
    <div class="flex items-start justify-between gap-4">
      <div>
        <p class="eyebrow">私密研究项目 · ID {{ g.id }}</p>
        <h1 class="text-2xl mt-1">{{ g.name_zh }}</h1>
        <p class="text-gray-500 mt-1">{{ g.desc_zh || '暂无项目介绍' }}</p>
        <p class="text-xs text-gray-400 mt-2">仅 {{ g.member_count }} 位受邀成员可见 · 研究项目权限不等于数据集管理权限</p>
      </div>
      <div class="flex gap-2">
        <button v-if="g.is_admin" class="btn-ghost" @click="openEdit">编辑研究项目</button>
        <button v-if="g.is_lead" class="btn-ghost text-red-600" @click="deleteProject">删除</button>
      </div>
    </div>

    <div class="mt-6 flex gap-1 overflow-x-auto border-b border-line">
      <button v-for="[key,label] in tabs" :key="key" class="px-3 py-2 text-sm whitespace-nowrap border-b-2"
        :class="tab===key?'border-accent text-accent':'border-transparent text-gray-500'" @click="tab=key">{{ label }}</button>
    </div>

    <section v-if="tab==='overview'" class="mt-6 grid md:grid-cols-3 gap-4">
      <div class="card md:col-span-2"><div class="label-cap">项目介绍</div><p class="mt-2 whitespace-pre-wrap">{{ g.desc_zh || '暂无项目介绍。Owner/Admin 可在右上角编辑。' }}</p></div>
      <div class="card"><div class="label-cap">项目负责人</div><p class="mt-2">{{ g.founder?.name }}</p><p class="text-sm text-gray-500">{{ g.founder?.contact }}</p></div>
      <div class="card"><div class="text-2xl">{{ g.members.length }}</div><div class="text-xs text-gray-400 mt-1">项目成员</div></div>
      <div class="card"><div class="text-2xl">{{ g.datasets.length }}</div><div class="text-xs text-gray-400 mt-1">内部数据集</div></div>
      <div class="card"><div class="text-2xl">{{ g.timeline.length }}</div><div class="text-xs text-gray-400 mt-1">时间线记录</div></div>
    </section>

    <section v-if="tab==='members'" class="mt-6">
      <div v-if="canInvite" class="card mb-4">
        <div class="label-cap">邀请平台成员</div>
        <div class="flex gap-2 mt-2"><input v-model="inviteQ" class="input" placeholder="姓名、用户名或 ID" @keyup.enter="searchUsers"><button class="btn-primary" @click="searchUsers">检索</button></div>
        <div v-if="inviteResults.length" class="mt-2 divide-y divide-line">
          <div v-for="u in inviteResults" :key="u.id" class="py-2 flex items-center gap-2 text-sm"><span>{{ u.display_name }}</span><span class="text-gray-400">@{{ u.username }} · ID {{ u.id }}</span><button class="btn-ghost text-xs ml-auto" @click="invite(u.id)">邀请</button></div>
        </div>
      </div>
      <div class="rounded-lg border border-line bg-white divide-y divide-line">
        <div v-for="m in g.members" :key="m.user_id" class="px-4 py-3 flex items-center gap-2 text-sm">
          <router-link :to="`/users/${m.user_id}`" class="text-accent">{{ m.name }}</router-link><span class="tag">{{ roleLabel(m) }}</span>
          <div class="ml-auto flex gap-2" v-if="!m.is_lead">
            <button v-if="g.is_lead && !m.is_admin" class="btn-ghost text-xs" @click="addAdmin(m.user_id)">设为 Admin</button>
            <button v-if="g.is_lead && m.is_admin" class="btn-ghost text-xs" @click="removeAdmin(m.user_id)">取消 Admin</button>
            <button v-if="g.is_lead" class="btn-ghost text-xs" @click="transferLead(m.user_id)">移交 Owner</button>
            <button v-if="g.is_admin && (!m.is_admin || g.is_lead)" class="text-xs text-accent2" @click="removeMember(m.user_id)">移除</button>
          </div>
        </div>
      </div>
    </section>

    <section v-if="tab==='datasets'" class="mt-6">
      <div class="flex justify-between items-center mb-3"><div><h2>内部数据集</h2><p class="text-xs text-gray-500">仅本研究项目成员可见；创建者自动成为数据集总管理员。</p></div><button class="btn-primary" @click="showDataset=true">＋新建数据集</button></div>
      <div class="grid md:grid-cols-3 gap-4"><div v-for="d in g.datasets" :key="d.id" class="card cursor-pointer hover:text-accent" @click="router.push(`/datasets/${d.slug}`)">{{ d.name_zh }}</div></div>
      <p v-if="!g.datasets.length" class="text-gray-400 text-sm">暂无内部数据集。</p>
    </section>

    <section v-if="tab==='links'" class="mt-6">
      <div class="card mb-4"><div class="label-cap">新增 Overleaf / 研究链接</div><div class="grid md:grid-cols-[1fr_2fr_auto] gap-2 mt-2"><input v-model="linkForm.title" class="input" placeholder="显示标题"><input v-model="linkForm.url" class="input" placeholder="https://..."><button class="btn-primary" @click="addLink">保存</button></div></div>
      <div class="space-y-2"><div v-for="x in g.links" :key="x.id" class="card py-3 flex items-center gap-3"><a :href="x.url" target="_blank" rel="noopener" class="text-accent hover:underline">{{ x.title }} ↗</a><div class="ml-auto flex gap-2"><button class="btn-ghost text-xs" @click="editLink(x)">修改</button><button class="text-xs text-accent2" @click="delLink(x.id)">删除</button></div></div></div>
    </section>

    <section v-if="tab==='timeline'" class="mt-6 grid md:grid-cols-[320px_1fr] gap-5">
      <div class="card h-fit"><div class="label-cap">记录研究进展</div><select v-model="timelineForm.category" class="input mt-2"><option v-for="(v,k) in categoryName" :key="k" :value="k">{{ v }}</option></select><input v-model="timelineForm.title" class="input mt-2" placeholder="标题"><textarea v-model="timelineForm.body" class="input mt-2" rows="5" placeholder="进展、关键问题、讨论结论或待办"></textarea><input type="file" class="text-xs mt-2" @change="timelineFile=($event.target as HTMLInputElement).files?.[0]||null"><button class="btn-primary w-full mt-3" @click="addTimeline">添加到时间线</button></div>
      <div class="space-y-3"><article v-for="e in g.timeline" :key="e.id" class="card"><div class="flex gap-2"><span class="tag">{{ categoryName[e.category]||e.category }}</span><span class="text-xs text-gray-400 ml-auto">{{ formatChinaDateTime(e.created_at) }}</span></div><h3 class="mt-2">{{ e.title }}</h3><p class="text-sm text-gray-600 whitespace-pre-wrap mt-1">{{ e.body }}</p><button v-if="e.has_file" class="text-xs text-accent mt-2" @click="downloadFile(`/groups/${slug()}/timeline/${e.id}/file`,e.file_name)">下载附件 · {{ e.file_name }}</button><p class="text-xs text-gray-400 mt-2">{{ e.author_name }}</p></article><p v-if="!g.timeline.length" class="text-gray-400 text-sm">暂无时间线记录。</p></div>
    </section>

    <section v-if="tab==='files'" class="mt-6">
      <div class="card mb-4 flex items-center gap-3"><input type="file" class="text-sm" @change="projectFile=($event.target as HTMLInputElement).files?.[0]||null"><button class="btn-primary ml-auto" @click="uploadFile">上传文件</button></div>
      <div class="rounded-lg border border-line bg-white divide-y divide-line"><div v-for="f in g.files" :key="f.id" class="px-4 py-3 flex items-center gap-3 text-sm"><button class="text-accent hover:underline" @click="downloadFile(`/groups/${slug()}/files/${f.id}/download`,f.file_name)">{{ f.file_name }}</button><span class="text-gray-400">{{ f.author_name }} · {{ formatChinaDate(f.created_at) }}</span><button class="text-xs text-accent2 ml-auto" @click="delFile(f.id)">删除</button></div></div>
      <p v-if="!g.files.length" class="text-gray-400 text-sm mt-3">暂无共享文件。</p>
    </section>

    <section v-if="tab==='discussion'" class="mt-6">
      <div class="flex items-center justify-between mb-4">
        <div><h2>内部讨论</h2><p class="text-xs text-gray-500 mt-1">仅研究项目成员可见，不进入全站研究讨论区；支持点赞、评论和回复评论。</p></div>
        <button class="btn-primary" @click="newDiscussion">＋发布内部讨论</button>
      </div>
      <PostCard v-for="p in projectPosts" :key="p.id" :post="p" :current-user-id="auth.user?.id"
        @edit="editDiscussion" @deleted="postDeleted" @changed="load" />
      <p v-if="!projectPosts.length" class="text-gray-400 text-sm">暂无内部讨论。</p>
    </section>

    <div v-if="showDataset" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"><div class="bg-white rounded-lg max-w-md w-full p-6 m-4"><h3 class="text-lg">新建内部数据集</h3><p class="text-xs text-gray-500 mb-3">创建后仅研究项目成员可见，你将成为数据集总管理员。</p><input v-model="dsForm.name_zh" class="input mb-2" placeholder="数据集名称"><textarea v-model="dsForm.desc_zh" class="input mb-3" placeholder="简介"></textarea><div class="flex justify-end gap-2"><button class="btn-ghost" @click="showDataset=false">取消</button><button class="btn-primary" @click="createDataset">创建</button></div></div></div>
    <div v-if="showEdit" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"><div class="bg-white rounded-lg max-w-md w-full p-6 m-4"><h3 class="text-lg mb-3">编辑研究项目</h3><input v-model="editForm.name_zh" class="input mb-2" placeholder="项目名称"><textarea v-model="editForm.desc_zh" class="input mb-3" rows="5" placeholder="项目介绍"></textarea><div class="flex justify-end gap-2"><button class="btn-ghost" @click="showEdit=false">取消</button><button class="btn-primary" @click="saveEdit">保存</button></div></div></div>
    <PostComposer v-if="composerOpen" :edit="editingPost"
      :context="{ groupId:g.id, groupName:g.name_zh, internal:true }"
      @close="composerOpen=false" @saved="load" />
  </div>
</template>
