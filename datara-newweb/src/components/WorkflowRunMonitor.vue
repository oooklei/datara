<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  cancelWorkflowRun,
  getWorkflowRunLogs,
  getWorkflowRunStat,
  listWorkflowRunStats,
  rerunWorkflowInstance,
  type WorkflowInstanceType,
  type WorkflowRunLogLine,
  type WorkflowRunStatQuery,
  type WorkflowRunReconcileDetail,
  type WorkflowRunStat,
} from '../services/rebuild/executionStatsApi'

const props = defineProps<{
  projectId: number
  /** D8 下钻契约：来自工作台/深链 ?status= 的初始状态过滤（后端词形 SUCCEEDED/FAILED/RUNNING…） */
  initialStatus?: string
  /** D8 下钻契约：来自最近实例 ?runId= 的单实例定位（单查 run-stats/{id}，不走列表过滤） */
  initialRunId?: number
}>()
const rows = ref<WorkflowRunStat[]>([])
const loading = ref(false)
const error = ref('')
/** D13 列表搜索：对当前页运行记录前端过滤，不触发后端。 */
const filterKeyword = ref('')
const filteredRows = computed(() => {
  const keyword = filterKeyword.value.toLowerCase()
  if (keyword === '') return rows.value
  return rows.value.filter(
    (row) =>
      (row.dag_name || `#${row.workflow_id}`).toLowerCase().includes(keyword) ||
      String(row.workflow_id).toLowerCase().includes(keyword) ||
      row.instance_type.toLowerCase().includes(keyword) ||
      row.status.toLowerCase().includes(keyword),
  )
})
const instanceType = ref<'' | WorkflowInstanceType>('')
const statusFilter = ref(props.initialStatus ?? '')
const drillRunId = ref<number | null>(props.initialRunId ?? null)
const pageOffset = ref(0)
const pageSize = 50
const total = ref(0)
let loadGeneration = 0
let detailGeneration = 0
const expandedId = ref<number | null>(null)
const details = ref<WorkflowRunReconcileDetail[]>([])
const detailLoading = ref(false)
const detailError = ref('')

/* ---- T6 运行监控日志通道（审计弹窗 #9 LogPanel）----
 * 后端无 SSE 端点 → 日志走 3s 轮询：RUNNING/PENDING 持续轮询，终态单拉即停。
 * generation + projectId + instanceId 三重守卫，迟到的轮询响应一律丢弃。
 */
const LOG_POLL_MS = 3000
const RUN_TERMINAL_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'SKIPPED'])
const RUN_ACTIVE_STATUSES = new Set(['RUNNING', 'PENDING'])
const logs = ref<WorkflowRunLogLine[]>([])
const logsInstanceId = ref<number | null>(null)
const runStatus = ref('')
const logsLoading = ref(false)
const logsError = ref('')
let logGeneration = 0
let logTimer: number | null = null

const logsText = computed(() => logs.value.map((line) => `[${line.level}] ${line.message}`).join('\n'))
const logLive = computed(() => logsInstanceId.value !== null && !RUN_TERMINAL_STATUSES.has(runStatus.value))

function stopLogPolling() {
  if (logTimer !== null) {
    window.clearInterval(logTimer)
    logTimer = null
  }
}

async function refreshLogs(projectId: number, instanceId: number, generation: number) {
  logsLoading.value = true
  try {
    const result = await getWorkflowRunLogs(projectId, instanceId)
    if (generation !== logGeneration || projectId !== props.projectId || logsInstanceId.value !== instanceId) return
    logs.value = result.logs
    runStatus.value = result.status
    logsError.value = ''
    if (RUN_TERMINAL_STATUSES.has(result.status)) stopLogPolling()
  } catch (reason) {
    if (generation !== logGeneration || projectId !== props.projectId || logsInstanceId.value !== instanceId) return
    logsError.value = reason instanceof Error ? reason.message : '运行日志加载失败'
  } finally {
    if (generation === logGeneration) logsLoading.value = false
  }
}

function openLogs(row: WorkflowRunStat) {
  const instanceId = row.workflow_instance_id
  stopLogPolling()
  logGeneration += 1
  logsInstanceId.value = instanceId
  runStatus.value = row.status
  logs.value = []
  logsError.value = ''
  void refreshLogs(props.projectId, instanceId, logGeneration)
  if (!RUN_TERMINAL_STATUSES.has(row.status)) {
    logTimer = window.setInterval(() => {
      void refreshLogs(props.projectId, instanceId, logGeneration)
    }, LOG_POLL_MS)
  }
}

function closeLogs() {
  stopLogPolling()
  logGeneration += 1
  logsInstanceId.value = null
  runStatus.value = ''
  logs.value = []
  logsLoading.value = false
  logsError.value = ''
}

function refreshLogsManually() {
  const instanceId = logsInstanceId.value
  if (instanceId === null) return
  void refreshLogs(props.projectId, instanceId, logGeneration)
}

onBeforeUnmount(stopLogPolling)

function isStoppable(row: WorkflowRunStat) {
  return RUN_ACTIVE_STATUSES.has(row.status)
}

function isRerunnable(row: WorkflowRunStat) {
  // FORMAL 携 run-stats 行的 workflow_version_id（已发布版本）重跑；STREAM version=0 由后端处理
  if (row.instance_type === 'FORMAL' && !row.workflow_version_id) return false
  return !RUN_ACTIVE_STATUSES.has(row.status)
}

async function onStopRun(row: WorkflowRunStat) {
  try {
    await ElMessageBox.confirm(`停止运行实例 #${row.workflow_instance_id}？`, '停止运行', { type: 'warning' })
  } catch {
    return
  }
  try {
    await cancelWorkflowRun(props.projectId, row.workflow_instance_id)
    ElMessage.success('已发出停止指令，实例将进入 CANCELLED')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '停止失败')
  }
}

async function onRerunRun(row: WorkflowRunStat) {
  const rerunType = row.instance_type === 'STREAM' ? 'STREAM' : 'FORMAL'
  const label = rerunType === 'STREAM' ? '流处理' : '正式运行'
  try {
    await ElMessageBox.confirm(`重跑${label}（工作流 #${row.workflow_id}）？`, '重跑', { type: 'info' })
  } catch {
    return
  }
  try {
    await rerunWorkflowInstance(
      props.projectId,
      row.workflow_id,
      rerunType,
      rerunType === 'FORMAL' ? row.workflow_version_id ?? undefined : undefined,
    )
    ElMessage.success('已发起新一轮运行')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '重跑失败')
  }
}

function resetDetails() {
  detailGeneration += 1
  expandedId.value = null
  details.value = []
  detailLoading.value = false
  detailError.value = ''
  closeLogs()
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
    // D8 runId 契约：单实例定位走 run-stats/{id} 单查（后端列表无 run_id 过滤参数），
    // 拉平为单行展示且可展开对账明细；任何单查失败都回落空态而不是整页报错。
    if (drillRunId.value !== null) {
      const one = await getWorkflowRunStat(projectId, drillRunId.value)
      if (generation !== loadGeneration || projectId !== props.projectId) return
      rows.value = [one]
      total.value = 1
      return
    }
    const options: WorkflowRunStatQuery = {}
    if (instanceType.value) options.instanceType = instanceType.value
    if (statusFilter.value) options.status = statusFilter.value
    if (pageOffset.value > 0) {
      options.offset = pageOffset.value
      options.limit = pageSize
    }
    const result = Object.keys(options).length
      ? await listWorkflowRunStats(projectId, options)
      : await listWorkflowRunStats(projectId)
    if (generation !== loadGeneration || projectId !== props.projectId) return
    rows.value = result.items
    total.value = Number(result.total ?? result.items.length)
  } catch (reason) {
    if (generation !== loadGeneration || projectId !== props.projectId) return
    error.value = reason instanceof Error ? reason.message : '运行记录加载失败'
    ElMessage.error(error.value)
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function applyFilters() {
  pageOffset.value = 0
  resetDetails()
  void load()
}

function previousPage() {
  if (pageOffset.value === 0) return
  pageOffset.value = Math.max(0, pageOffset.value - pageSize)
  void load()
}

function nextPage() {
  if (pageOffset.value + pageSize >= total.value) return
  pageOffset.value += pageSize
  void load()
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
  openLogs(row)
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
watch(() => props.projectId, () => {
  pageOffset.value = 0
  total.value = 0
  void load()
}, { immediate: true })

// D8 深链变化（KeepAlive 下 route.query.status/runId 变化经 props 透传进来）：
// 重置过滤与翻页后按新契约重载，保证书签/工作台下钻始终落到当前参数。
watch(() => [props.initialStatus, props.initialRunId] as const, ([nextStatus, nextRunId]) => {
  const next = nextStatus ?? ''
  const nextId = nextRunId ?? null
  if (next === statusFilter.value && nextId === drillRunId.value) return
  statusFilter.value = next
  drillRunId.value = nextId
  pageOffset.value = 0
  total.value = 0
  void load()
})
</script>

<template>
  <section class="run-monitor" data-workflow-run-monitor>
    <header><div><h3>工作流运行监控</h3><p>统一记录每次工作流的成功、失败和跳过数量</p></div><button :disabled="loading" @click="load">刷新</button></header>
    <div class="run-monitor-filters" data-run-monitor-filters>
      <label>实例类型
        <select v-model="instanceType" data-run-instance-type @change="applyFilters">
          <option value="">全部</option>
          <option value="FORMAL">正式运行</option>
          <option value="STREAM">流处理</option>
        </select>
      </label>
      <label>状态
        <select v-model="statusFilter" data-run-status @change="applyFilters">
          <option value="">全部</option>
          <option value="SUCCEEDED">成功</option>
          <option value="FAILED">失败</option>
          <option value="RUNNING">运行中</option>
          <option value="PENDING">等待中</option>
          <option value="CANCELLED">已取消</option>
        </select>
      </label>
      <label>关键字
        <input v-model.trim="filterKeyword" data-filter-keyword data-run-keyword placeholder="搜索工作流、ID、类型或状态">
      </label>
    </div>
    <p v-if="loading" data-run-loading>加载中…</p>
    <p v-else-if="error" data-run-error>{{ error }} <button @click="load">重试</button></p>
    <p v-else-if="!rows.length" data-run-empty>暂无运行记录</p>
    <table v-else><thead><tr><th>工作流</th><th>类型</th><th>状态</th><th>源数据量</th><th>目标数据量</th><th>成功</th><th>失败</th><th>跳过</th><th>总数</th><th>开始时间</th><th>对账</th><th>操作</th></tr></thead><tbody>
      <tr v-if="filteredRows.length === 0"><td colspan="12">无匹配运行记录</td></tr>
      <template v-for="row in filteredRows" :key="row.id">
        <tr><td>{{ row.dag_name || `#${row.workflow_id}` }}</td><td>{{ row.instance_type }}</td><td>{{ row.status }}</td><td>{{ row.source_count ?? '—' }}</td><td>{{ row.target_count ?? '—' }}</td><td>{{ row.success_count }}</td><td>{{ row.failure_count }}</td><td>{{ row.skipped_count }}</td><td>{{ row.total_count }}</td><td>{{ row.started_at }}</td><td><button type="button" :aria-expanded="expandedId === row.id" @click="toggleDetails(row)">{{ expandedId === row.id ? '收起' : '查看明细' }}</button></td><td class="run-actions"><button v-if="isStoppable(row)" type="button" data-run-stop @click="onStopRun(row)">停止</button><button v-if="isRerunnable(row)" type="button" data-run-rerun @click="onRerunRun(row)">重跑</button></td></tr>
        <tr v-if="expandedId === row.id" class="detail-row" data-run-stat-details><td colspan="12">
          <p v-if="detailLoading">明细加载中…</p>
          <p v-else-if="detailError" data-detail-error>{{ detailError }}</p>
          <p v-else-if="!details.length" data-detail-empty>本次运行无表级对账明细</p>
          <table v-else class="detail-table"><thead><tr><th>源对象</th><th>目标对象</th><th>源数据量</th><th>目标数据量</th><th>成功</th><th>失败</th><th>差异</th></tr></thead><tbody><tr v-for="detail in details" :key="detail.id"><td>{{ detail.source_object }}</td><td>{{ detail.target_object }}</td><td>{{ detail.source_count ?? '—' }}</td><td>{{ detail.target_count ?? '—' }}</td><td>{{ detail.success_count }}</td><td>{{ detail.failure_count }}</td><td>{{ detail.difference_count ?? '—' }}</td></tr></tbody></table>
          <div class="run-logs" data-run-logs>
            <header class="run-logs-header">
              <strong>运行日志</strong>
              <span v-if="logLive" class="run-logs-live" data-run-logs-live>轮询中（3s）</span>
              <button type="button" data-run-logs-refresh @click="refreshLogsManually">刷新</button>
            </header>
            <p v-if="logsLoading" data-run-logs-loading>日志加载中…</p>
            <p v-else-if="logsError" data-run-logs-error>{{ logsError }}</p>
            <p v-else-if="!logs.length" data-run-logs-empty>暂无日志</p>
            <pre v-else class="run-logs-body" data-run-logs-body>{{ logsText }}</pre>
          </div>
        </td></tr>
      </template>
    </tbody></table>
    <nav v-if="total > pageSize" class="run-monitor-pagination" data-run-pagination aria-label="运行记录分页">
      <button type="button" data-run-previous :disabled="loading || pageOffset === 0" @click="previousPage">上一页</button>
      <span>{{ pageOffset + 1 }}–{{ Math.min(pageOffset + pageSize, total) }} / {{ total }}</span>
      <button type="button" data-run-next :disabled="loading || pageOffset + pageSize >= total" @click="nextPage">下一页</button>
    </nav>
  </section>
</template>

<style scoped>
.run-monitor { padding: 20px; background: var(--card); color: var(--text); }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
h3, p { margin: 0; } header p { margin-top: 4px; color: var(--text-3); font-size: 12px; }
button { border: 1px solid var(--border-strong); background: var(--card); border-radius: 5px; padding: 5px 12px; cursor: pointer; }
.run-monitor-filters { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.run-monitor-filters label { display: flex; align-items: center; gap: 6px; color: var(--text-2); font-size: 12px; }
.run-monitor-filters select { min-width: 128px; padding: 5px 8px; border: 1px solid var(--border-strong); border-radius: 5px; background: var(--card); }
.run-monitor-pagination { display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-top: 12px; color: var(--text-3); font-size: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; } th, td { padding: 8px; text-align: left; border-bottom: 1px solid var(--border); }
.detail-row > td { padding: 12px 16px; background: var(--bg); }
.detail-table th, .detail-table td { padding: 6px 8px; }
.run-actions { white-space: nowrap; }
.run-logs { margin-top: 10px; }
.run-logs-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; font-size: 12px; color: var(--text-2); }
.run-logs-live { color: var(--primary); }
.run-logs-body { margin: 0; padding: 8px 10px; background: var(--log-bg); color: var(--log-fg); border-radius: 5px; font-size: 12px; line-height: 1.6; max-height: 240px; overflow: auto; white-space: pre-wrap; }
</style>
