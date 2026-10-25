<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getWorkflowRunStat,
  listWorkflowRunStats,
  type WorkflowRunReconcileDetail,
  type WorkflowRunStat,
} from '../services/rebuild/executionStatsApi'

const props = defineProps<{ projectId: number }>()
const rows = ref<WorkflowRunStat[]>([])
const loading = ref(false)
const error = ref('')
let loadGeneration = 0
let detailGeneration = 0
const expandedId = ref<number | null>(null)
const details = ref<WorkflowRunReconcileDetail[]>([])
const detailLoading = ref(false)
const detailError = ref('')

function resetDetails() {
  detailGeneration += 1
  expandedId.value = null
  details.value = []
  detailLoading.value = false
  detailError.value = ''
}

async function load() {
  const generation = ++loadGeneration
  const projectId = props.projectId
  loading.value = true; error.value = ''
  // Clear the previous project's rows immediately.  This matters when a
  // keep-alive project route changes: showing old counters during the request
  // is misleading, and a slower response must never overwrite the new scope.
  rows.value = []
  resetDetails()
  try {
    const result = await listWorkflowRunStats(projectId)
    if (generation !== loadGeneration || projectId !== props.projectId) return
    rows.value = result.items
  } catch (reason) {
    if (generation !== loadGeneration || projectId !== props.projectId) return
    error.value = reason instanceof Error ? reason.message : '运行记录加载失败'
    ElMessage.error(error.value)
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

async function toggleDetails(row: WorkflowRunStat) {
  if (expandedId.value === row.id) {
    resetDetails()
    return
  }
  const generation = ++detailGeneration
  const projectId = props.projectId
  expandedId.value = row.id
  details.value = []
  detailError.value = ''
  detailLoading.value = true
  try {
    const result = await getWorkflowRunStat(projectId, row.id)
    if (generation !== detailGeneration || projectId !== props.projectId || expandedId.value !== row.id) return
    details.value = result.details
  } catch (reason) {
    if (generation !== detailGeneration || projectId !== props.projectId || expandedId.value !== row.id) return
    detailError.value = reason instanceof Error ? reason.message : '对账明细加载失败'
  } finally {
    if (generation === detailGeneration) detailLoading.value = false
  }
}
// ProjectSegmentView is kept alive while switching project routes.  Watching the
// project id prevents the monitor from showing the previous project's run rows.
watch(() => props.projectId, () => { void load() }, { immediate: true })
</script>

<template>
  <section class="run-monitor" data-workflow-run-monitor>
    <header><div><h3>工作流运行监控</h3><p>统一记录每次工作流的成功、失败和跳过数量</p></div><button :disabled="loading" @click="load">刷新</button></header>
    <p v-if="loading" data-run-loading>加载中…</p>
    <p v-else-if="error" data-run-error>{{ error }} <button @click="load">重试</button></p>
    <p v-else-if="!rows.length" data-run-empty>暂无运行记录</p>
    <table v-else><thead><tr><th>工作流</th><th>类型</th><th>状态</th><th>源数据量</th><th>目标数据量</th><th>成功</th><th>失败</th><th>跳过</th><th>总数</th><th>开始时间</th><th>对账</th></tr></thead><tbody>
      <template v-for="row in rows" :key="row.id">
        <tr><td>{{ row.dag_name || `#${row.workflow_id}` }}</td><td>{{ row.instance_type }}</td><td>{{ row.status }}</td><td>{{ row.source_count ?? '—' }}</td><td>{{ row.target_count ?? '—' }}</td><td>{{ row.success_count }}</td><td>{{ row.failure_count }}</td><td>{{ row.skipped_count }}</td><td>{{ row.total_count }}</td><td>{{ row.started_at }}</td><td><button type="button" :aria-expanded="expandedId === row.id" @click="toggleDetails(row)">{{ expandedId === row.id ? '收起' : '查看明细' }}</button></td></tr>
        <tr v-if="expandedId === row.id" class="detail-row" data-run-stat-details><td colspan="11">
          <p v-if="detailLoading">明细加载中…</p>
          <p v-else-if="detailError" data-detail-error>{{ detailError }}</p>
          <p v-else-if="!details.length" data-detail-empty>本次运行无表级对账明细</p>
          <table v-else class="detail-table"><thead><tr><th>源对象</th><th>目标对象</th><th>源数据量</th><th>目标数据量</th><th>成功</th><th>失败</th><th>差异</th></tr></thead><tbody><tr v-for="detail in details" :key="detail.id"><td>{{ detail.source_object }}</td><td>{{ detail.target_object }}</td><td>{{ detail.source_count ?? '—' }}</td><td>{{ detail.target_count ?? '—' }}</td><td>{{ detail.success_count }}</td><td>{{ detail.failure_count }}</td><td>{{ detail.difference_count ?? '—' }}</td></tr></tbody></table>
        </td></tr>
      </template>
    </tbody></table>
  </section>
</template>

<style scoped>
.run-monitor { padding: 20px; background: #fff; color: #172033; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
h3, p { margin: 0; } header p { margin-top: 4px; color: #64748b; font-size: 12px; }
button { border: 1px solid #cbd5e1; background: #fff; border-radius: 5px; padding: 5px 12px; cursor: pointer; }
table { width: 100%; border-collapse: collapse; font-size: 13px; } th, td { padding: 8px; text-align: left; border-bottom: 1px solid #e5e7eb; }
.detail-row > td { padding: 12px 16px; background: #f8fafc; }
.detail-table th, .detail-table td { padding: 6px 8px; }
</style>
