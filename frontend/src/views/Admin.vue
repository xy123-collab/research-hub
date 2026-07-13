<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
const board = ref<any[]>([]); const audit = ref<any[]>([]); const supers = ref<any[]>([])
const err = ref(''); const newSuper = ref<number | null>(null)
onMounted(load)
async function load() {
  try { board.value = (await api.get('/admin/contributions', { params: { scope: 'total' } })).data } catch(e:any){ err.value = e.response?.data?.detail }
  try { audit.value = (await api.get('/admin/audit-log', { params: { limit: 30 } })).data } catch {}
  try { supers.value = (await api.get('/admin/super-admins')).data } catch {}
}
async function addSuper() {
  if (!newSuper.value) return
  try { await api.post('/admin/super-admins', null, { params: { uid: newSuper.value } }); newSuper.value = null; load() }
  catch (e: any) { alert(e.response?.data?.detail || '失败') }
}
</script>
<template>
  <h1 class="text-2xl mb-4">管理后台</h1>
  <p class="text-xs text-gray-500 mb-4">总管理员=平台维护者：只见元信息与动作元数据审计，看不到课题组/数据内部内容与贡献明细，不能单方面删数据。贡献总览归课题组管理员。</p>

  <section class="mb-6">
    <h2 class="text-lg mb-2">全员总贡献度（课题组管理员视图）</h2>
    <div class="card">
      <p v-if="err" class="text-accent2 text-sm">{{ err }}</p>
      <table v-else class="w-full text-sm">
        <tr class="text-left label-cap"><th class="py-1">用户</th><th>贡献度</th></tr>
        <tr v-for="r in board" :key="r.user_id" class="border-t border-line">
          <td class="py-1"><router-link :to="`/users/${r.user_id}`" class="text-accent">#{{ r.user_id }}</router-link></td>
          <td class="font-mono">{{ r.score }}</td>
        </tr>
      </table>
    </div>
  </section>

  <section class="mb-6" v-if="supers.length">
    <h2 class="text-lg mb-2">总管理员（可多个·可交接）</h2>
    <div class="card text-sm">
      <div class="mb-3"><span v-for="s in supers" :key="s.id" class="tag mr-2">{{ s.display_name }}（#{{ s.id }}）</span></div>
      <div class="flex items-center gap-2">
        <input v-model.number="newSuper" type="number" class="input w-40" placeholder="用户 ID" />
        <button class="btn-primary text-sm" @click="addSuper">添加/交接总管理员</button>
      </div>
      <p class="text-xs text-gray-400 mt-2">按用户 ID 添加总管理员。总管理员只负责平台运行，不接触课题组/数据集内容。</p>
    </div>
  </section>

  <section v-if="audit.length">
    <h2 class="text-lg mb-2">全站审计日志（动作元数据）</h2>
    <div class="card">
      <table class="w-full text-xs">
        <tr v-for="l in audit" :key="l.id" class="border-t border-line">
          <td class="py-1">#{{ l.user_id }}</td><td><span class="tag">{{ l.action }}</span></td>
          <td>{{ l.object_type }} {{ l.object_id }}</td><td class="text-gray-400">{{ l.created_at?.slice(0,19) }}</td>
        </tr>
      </table>
    </div>
  </section>
</template>
