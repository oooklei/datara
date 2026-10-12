<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { diffModelVersion, listModelVersions, rollbackModelVersion, saveModelVersion, type ModelVersion } from '../../services/modelApi'

const route = useRoute(); const router = useRouter()
const id = String(route.params.id)
const rows = ref<ModelVersion[]>([]); const note = ref(''); const loading = ref(false)
async function load() { loading.value = true; try { rows.value = await listModelVersions(id) } finally { loading.value = false } }
async function save() { await saveModelVersion(id, note.value); note.value = ''; await load(); ElMessage.success('版本快照已保存') }
async function diff(row: ModelVersion) { const d = await diffModelVersion(id, row.id); ElMessage.info(`新增 ${d.added.length}、删除 ${d.removed.length}、变更 ${d.changed.length} 个字段`) }
async function rollback(row: ModelVersion) { await ElMessageBox.confirm(`回滚到 v${row.version} 将生成新的草稿版本，是否继续？`, '版本回滚'); await rollbackModelVersion(id, row.id); await load(); ElMessage.success('已生成回滚草稿') }
onMounted(load)
</script>

<template>
  <div class="page version-page">
    <div class="page-head"><button @click="router.back()">← 返回</button><h2>模型版本管理</h2></div>
    <div class="toolbar"><input v-model="note" placeholder="变更说明（可选）" /><button class="primary" :disabled="loading" @click="save">保存当前快照</button></div>
    <table><thead><tr><th>版本</th><th>变更说明</th><th>创建人</th><th>时间</th><th>操作</th></tr></thead>
      <tbody><tr v-for="r in rows" :key="r.id"><td>v{{ r.version }}</td><td>{{ r.changeNote || '—' }}</td><td>{{ r.createdBy }}</td><td>{{ r.createdAt || '—' }}</td><td><button @click="diff(r)">差异</button><button @click="rollback(r)">回滚</button></td></tr><tr v-if="!rows.length"><td colspan="5">暂无快照</td></tr></tbody>
    </table>
  </div>
</template>

<style scoped>
.version-page{padding:24px}.page-head{display:flex;align-items:center;gap:12px}.toolbar{display:flex;gap:8px;margin:18px 0}.toolbar input{width:280px;padding:8px}.primary{background:#2563eb;color:#fff;border:0;padding:8px 14px}table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #e5e7eb;text-align:left}td button{margin-right:8px}
</style>
