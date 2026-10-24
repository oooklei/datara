<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listWorkflowRunStats, type WorkflowRunStat } from '../services/rebuild/executionStatsApi'

const props = defineProps<{ projectId: number }>()
const rows = ref<WorkflowRunStat[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true; error.value = ''
  try { rows.value = (await listWorkflowRunStats(props.projectId)).items }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '运行记录加载失败'; ElMessage.error(error.value) }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <section class="run-monitor" data-workflow-run-monitor>
    <header><div><h3>工作流运行监控</h3><p>统一记录每次工作流的成功、失败和跳过数量</p></div><button :disabled="loading" @click="load">刷新</button></header>
    <p v-if="loading" data-run-loading>加载中…</p>
    <p v-else-if="error" data-run-error>{{ error }} <button @click="load">重试</button></p>
    <p v-else-if="!rows.length" data-run-empty>暂无运行记录</p>
    <table v-else><thead><tr><th>工作流</th><th>状态</th><th>成功</th><th>失败</th><th>跳过</th><th>总数</th><th>开始时间</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id"><td>{{ row.dag_name || `#${row.workflow_id}` }}</td><td>{{ row.status }}</td><td>{{ row.success_count }}</td><td>{{ row.failure_count }}</td><td>{{ row.skipped_count }}</td><td>{{ row.total_count }}</td><td>{{ row.started_at }}</td></tr></tbody></table>
  </section>
</template>

<style scoped>
.run-monitor { padding: 20px; background: #fff; color: #172033; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
h3, p { margin: 0; } header p { margin-top: 4px; color: #64748b; font-size: 12px; }
button { border: 1px solid #cbd5e1; background: #fff; border-radius: 5px; padding: 5px 12px; cursor: pointer; }
table { width: 100%; border-collapse: collapse; font-size: 13px; } th, td { padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb; }
</style>
