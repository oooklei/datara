<script setup lang="ts">
/**
 * 运行监控（datara 自建页，§10.5 B 类 / §10.7 B1、C1）。
 *
 * 海豚实例页不进 datara iframe（§10.10 R7），故实例列表 / 详情 / 甘特图 /
 * 任务实例 / 日志 / 停止·暂停·恢复·失败重试·重跑 全部由本页承载，数据源为
 * datara 编排网关（`orchestrationApi`，后端代理海豚 WorkflowInstanceController /
 * TaskInstanceController / LoggerController / ExecutorController）。
 *
 * 与同页签下的 `WorkflowRunMonitor` 区别：后者读 datara 自研 execution 域
 * （run-stats 对账数据），本页读海豚运行底座，两者互不替代。
 *
 * 可用性矩阵照抄海豚实例页 `views/projects/workflow/instance/components/table-action.tsx`
 * （L147-234），保证「与海豚原生一致」且不误放行。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  orchestrationApi,
  type InstanceGantt,
  type InstanceVariables,
  type TaskInstanceLog,
  type TaskInstanceRow,
  type WorkflowInstanceExecuteType,
  type WorkflowInstanceRow,
} from '../services/rebuild/orchestrationApi'

const props = defineProps<{ projectId: number }>()

const PAGE_SIZE = 10

/* ---- 海豚状态词表（照抄 dolphinscheduler-ui/src/common/types.ts） ---- */
const INSTANCE_STATE_LABELS: Record<string, string> = {
  SUBMITTED_SUCCESS: '提交成功',
  RUNNING_EXECUTION: '运行中',
  READY_PAUSE: '待暂停',
  PAUSE: '已暂停',
  READY_STOP: '待停止',
  STOP: '已停止',
  FAILURE: '失败',
  SUCCESS: '成功',
  SERIAL_WAIT: '串行等待',
  FAILOVER: '容错',
}
const INSTANCE_STATE_COLORS: Record<string, string> = {
  SUBMITTED_SUCCESS: '#94a3b8',
  RUNNING_EXECUTION: '#2563eb',
  READY_PAUSE: '#0d9488',
  PAUSE: '#d97706',
  READY_STOP: '#dc2626',
  STOP: '#475569',
  FAILURE: '#dc2626',
  SUCCESS: '#16a34a',
  SERIAL_WAIT: '#94a3b8',
  FAILOVER: '#7c3aed',
}
const TASK_STATE_LABELS: Record<string, string> = {
  SUBMITTED_SUCCESS: '提交成功',
  RUNNING_EXECUTION: '运行中',
  PAUSE: '已暂停',
  FAILURE: '失败',
  SUCCESS: '成功',
  NEED_FAULT_TOLERANCE: '需容错',
  KILL: '已杀死',
  DELAY_EXECUTION: '延迟执行',
  FORCED_SUCCESS: '强制成功',
  DISPATCH: '派发中',
}
const TASK_STATE_COLORS: Record<string, string> = {
  SUBMITTED_SUCCESS: '#94a3b8',
  RUNNING_EXECUTION: '#2563eb',
  PAUSE: '#d97706',
  FAILURE: '#dc2626',
  SUCCESS: '#16a34a',
  NEED_FAULT_TOLERANCE: '#7c3aed',
  KILL: '#475569',
  DELAY_EXECUTION: '#0d9488',
  FORCED_SUCCESS: '#16a34a',
  DISPATCH: '#2563eb',
}

function instanceStateLabel(state: string | null): string {
  return INSTANCE_STATE_LABELS[state ?? ''] ?? (state || '—')
}
function taskStateLabel(state: string | null): string {
  return TASK_STATE_LABELS[state ?? ''] ?? (state || '—')
}

/* ---- 可用性判定（海豚实例页 table-action.tsx 同构） ---- */
function canRerun(state: string | null): boolean {
  return state === 'SUCCESS' || state === 'PAUSE' || state === 'FAILURE' || state === 'STOP'
}
function canFailureRetry(state: string | null): boolean {
  return state === 'FAILURE'
}
function canStop(state: string | null): boolean {
  return state === 'RUNNING_EXECUTION' || state === 'STOP'
}
function canPause(state: string | null): boolean {
  return state === 'RUNNING_EXECUTION' || state === 'PAUSE'
}
/** 停止/暂停按钮在 STOP/PAUSE 态实际下发 RECOVER_SUSPENDED_PROCESS（恢复挂起）。 */
function controlFor(state: string | null, action: 'STOP' | 'PAUSE'): WorkflowInstanceExecuteType {
  if (state === 'STOP' || state === 'PAUSE') return 'RECOVER_SUSPENDED_PROCESS'
  return action
}

/* ---- 列表 ---- */
const rows = ref<WorkflowInstanceRow[]>([])
const loading = ref(false)
const error = ref('')
const pageNo = ref(1)
const total = ref(0)
const keyword = ref('')
const stateFilter = ref('')
/** 输入框草稿；`appliedKeyword` 才是已生效查询词（回车/点查询才生效）。 */
const appliedKeyword = ref('')
const rangeText = computed(() => {
  if (total.value === 0) return '0 / 0'
  const from = (pageNo.value - 1) * PAGE_SIZE + 1
  const to = Math.min(pageNo.value * PAGE_SIZE, total.value)
  return `${from}–${to} / ${total.value}`
})
let loadGeneration = 0

async function load() {
  const generation = ++loadGeneration
  loading.value = true
  error.value = ''
  try {
    const result = await orchestrationApi.listWorkflowInstances({
      projectId: props.projectId,
      pageNo: pageNo.value,
      pageSize: PAGE_SIZE,
      searchVal: appliedKeyword.value,
      stateType: stateFilter.value,
    })
    if (generation !== loadGeneration) return
    rows.value = result.list
    total.value = result.total
  } catch (reason) {
    if (generation !== loadGeneration) return
    rows.value = []
    total.value = 0
    error.value = reason instanceof Error ? reason.message : '实例列表加载失败'
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

function applyFilters() {
  appliedKeyword.value = keyword.value.trim()
  pageNo.value = 1
  void load()
}

function onPrevPage() {
  if (pageNo.value <= 1) return
  pageNo.value -= 1
  void load()
}

function onNextPage() {
  if (pageNo.value * PAGE_SIZE >= total.value) return
  pageNo.value += 1
  void load()
}

/* ---- 详情（任务实例 / 甘特 / 变量 / 日志） ---- */
const expandedId = ref<number | null>(null)
const tasks = ref<TaskInstanceRow[]>([])
const gantt = ref<InstanceGantt | null>(null)
const variables = ref<InstanceVariables | null>(null)
const detailLoading = ref(false)
const detailError = ref('')

const logs = ref<TaskInstanceLog[]>([])
const logTaskId = ref<number | null>(null)
const logsLoading = ref(false)
const logsError = ref('')

/** 任务条时间轴刻度：以甘特整体起止为基准做百分比定位，避免引入额外库。 */
const ganttScale = computed(() => {
  const items = gantt.value?.tasks ?? []
  const starts = items.flatMap((item) => item.startDate ?? [])
  const ends = items.flatMap((item) => item.endDate ?? [])
  const from = starts.length ? Math.min(...starts) : 0
  const to = ends.length ? Math.max(...ends) : 0
  return { from, to, span: to - from || 1 }
})
function ganttLeft(start: number): string {
  return `${(((start - ganttScale.value.from) / ganttScale.value.span) * 100).toFixed(2)}%`
}
function ganttWidth(start: number, end: number): string {
  const width = ((end - start) / ganttScale.value.span) * 100
  return `${Math.max(width, 1).toFixed(2)}%`
}

async function openDetail(row: WorkflowInstanceRow) {
  expandedId.value = row.id
  tasks.value = []
  gantt.value = null
  variables.value = null
  detailLoading.value = true
  detailError.value = ''
  closeLogs()
  try {
    // 三个请求互不依赖 → 并行发起（并行优化：避免串行等待拖长首屏）
    const [taskResult, ganttResult, variableResult] = await Promise.all([
      orchestrationApi.listTaskInstances({ projectId: props.projectId, pageNo: 1, pageSize: 200, workflowInstanceId: row.id }),
      orchestrationApi.getInstanceGantt(row.id, props.projectId),
      orchestrationApi.getInstanceVariables(row.id, props.projectId),
    ])
    tasks.value = taskResult.list
    gantt.value = ganttResult
    variables.value = variableResult
  } catch (reason) {
    detailError.value = reason instanceof Error ? reason.message : '实例详情加载失败'
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  expandedId.value = null
  tasks.value = []
  gantt.value = null
  variables.value = null
  detailError.value = ''
  closeLogs()
}

async function openLogs(row: TaskInstanceRow) {
  closeLogs()
  logsLoading.value = true
  logTaskId.value = row.id
  try {
    logs.value = await orchestrationApi.getTaskInstanceLog(row.id, props.projectId)
    logsError.value = ''
  } catch (reason) {
    logs.value = []
    logsError.value = reason instanceof Error ? reason.message : '任务日志加载失败'
  } finally {
    logsLoading.value = false
  }
}

function closeLogs() {
  logTaskId.value = null
  logs.value = []
  logsLoading.value = false
  logsError.value = ''
}

/* ---- 实例控制（§10.7 C1：停止/重跑/恢复可用） ---- */
async function runControl(row: WorkflowInstanceRow, executeType: WorkflowInstanceExecuteType, label: string) {
  try {
    await ElMessageBox.confirm(`确认对实例 #${row.id}「${row.name}」执行「${label}」？`, '实例控制', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await orchestrationApi.controlWorkflowInstance(row.id, props.projectId, executeType)
    ElMessage.success(`已下发「${label}」指令`)
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : `${label}失败`)
  }
}

watch(() => props.projectId, () => {
  pageNo.value = 1
  total.value = 0
  closeDetail()
  void load()
}, { immediate: true })

onBeforeUnmount(closeLogs)
</script>

<template>
  <section class="ds-run" data-ds-run-monitor>
    <header class="ds-run-head">
      <div>
        <h3 class="ds-run-title">工作流运行实例</h3>
        <p class="ds-run-sub">平台承载实例列表与详情；数据源为任务运行底座</p>
      </div>
      <button class="ds-btn" :disabled="loading" data-ds-run-refresh @click="load">刷新</button>
    </header>

    <div class="ds-run-filters" data-ds-run-filters>
      <input
        v-model.trim="keyword"
        class="ds-input"
        data-ds-run-keyword
        placeholder="按实例名称搜索"
        @keyup.enter="applyFilters"
      />
      <select v-model="stateFilter" class="ds-input" data-ds-run-state @change="applyFilters">
        <option value="">全部状态</option>
        <option v-for="(label, key) in INSTANCE_STATE_LABELS" :key="key" :value="key">{{ label }}</option>
      </select>
      <button class="ds-btn" :disabled="loading" data-ds-run-search @click="applyFilters">查询</button>
    </div>

    <p v-if="loading" class="ds-hint" data-ds-run-loading>加载中…</p>
    <p v-else-if="error" class="ds-hint" data-ds-run-error>{{ error }} <button class="ds-btn" @click="load">重试</button></p>
    <p v-else-if="!rows.length" class="ds-hint" data-ds-run-empty>暂无工作流运行实例（可先在画布点「启动」或「试运行」生成）</p>

    <table v-else class="ds-table" data-ds-run-table>
      <thead>
        <tr>
          <th>实例</th><th>状态</th><th>触发方式</th><th>试运行</th><th>调度时间</th>
          <th>开始时间</th><th>结束时间</th><th>耗时</th><th>执行人</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in rows" :key="row.id">
          <tr :data-ds-run-row="row.id">
            <td>
              <button class="ds-link" :aria-expanded="expandedId === row.id" data-ds-run-detail @click="expandedId === row.id ? closeDetail() : openDetail(row)">
                {{ expandedId === row.id ? '收起' : '详情' }}
              </button>
              <span class="ds-name">{{ row.name }}</span>
              <span class="ds-id">#{{ row.id }}</span>
            </td>
            <td>
              <span class="ds-badge" :style="{ color: INSTANCE_STATE_COLORS[row.state ?? ''] ?? '#475569' }" data-ds-run-state-badge>
                {{ instanceStateLabel(row.state) }}
              </span>
            </td>
            <td>{{ row.commandType ?? '—' }}</td>
            <td>{{ row.dryRun === 1 ? '试运行' : '正式' }}</td>
            <td>{{ row.scheduleTime ?? '—' }}</td>
            <td>{{ row.startTime ?? '—' }}</td>
            <td>{{ row.endTime ?? '—' }}</td>
            <td>{{ row.duration ?? '—' }}</td>
            <td>{{ row.executorName ?? '—' }}</td>
            <td class="ds-ops">
              <button v-if="canStop(row.state)" class="ds-btn" :data-ds-run-control="controlFor(row.state, 'STOP')" @click="runControl(row, controlFor(row.state, 'STOP'), row.state === 'STOP' ? '恢复挂起' : '停止')">
                {{ row.state === 'STOP' ? '恢复' : '停止' }}
              </button>
              <button v-if="canPause(row.state)" class="ds-btn" :data-ds-run-control="controlFor(row.state, 'PAUSE')" @click="runControl(row, controlFor(row.state, 'PAUSE'), row.state === 'PAUSE' ? '恢复挂起' : '暂停')">
                {{ row.state === 'PAUSE' ? '恢复' : '暂停' }}
              </button>
              <button v-if="canFailureRetry(row.state)" class="ds-btn" data-ds-run-failure-retry @click="runControl(row, 'START_FAILURE_TASK_PROCESS', '失败重试')">失败重试</button>
              <button v-if="canRerun(row.state)" class="ds-btn" data-ds-run-rerun @click="runControl(row, 'REPEAT_RUNNING', '重跑')">重跑</button>
            </td>
          </tr>
          <tr v-if="expandedId === row.id" class="ds-detail-row" :data-ds-run-detail-row="row.id">
            <td colspan="10">
              <p v-if="detailLoading" class="ds-hint" data-ds-run-detail-loading>详情加载中…</p>
              <p v-else-if="detailError" class="ds-hint" data-ds-run-detail-error>{{ detailError }}</p>
              <template v-else>
                <div class="ds-block" data-ds-run-gantt-block>
                  <strong class="ds-block-title">甘特图</strong>
                  <p v-if="!gantt?.tasks.length" class="ds-hint" data-ds-run-gantt-empty>暂无甘特数据</p>
                  <div v-else class="ds-gantt" data-ds-run-gantt>
                    <div v-for="(item, index) in gantt?.tasks ?? []" :key="`${item.taskName}-${index}`" class="ds-gantt-row">
                      <span class="ds-gantt-name" :title="item.taskName ?? ''">{{ item.taskName }}</span>
                      <span class="ds-gantt-track">
                        <i
                          v-for="(start, i) in item.startDate ?? []"
                          :key="i"
                          class="ds-gantt-bar"
                          :class="`ds-gantt-${item.status ?? 'unknown'}`"
                          :style="{ left: ganttLeft(start), width: ganttWidth(start, (item.endDate ?? [])[i] ?? start) }"
                        />
                      </span>
                    </div>
                  </div>
                </div>

                <div class="ds-block" data-ds-run-tasks-block>
                  <strong class="ds-block-title">任务实例</strong>
                  <p v-if="!tasks.length" class="ds-hint" data-ds-run-tasks-empty>暂无任务实例</p>
                  <table v-else class="ds-sub-table" data-ds-run-tasks>
                    <thead>
                      <tr><th>任务</th><th>类型</th><th>状态</th><th>提交时间</th><th>开始时间</th><th>结束时间</th><th>耗时</th><th>重试</th><th>主机</th><th>日志</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="task in tasks" :key="task.id" :data-ds-run-task="task.id">
                        <td>{{ task.name }}</td>
                        <td>{{ task.taskType ?? '—' }}</td>
                        <td>
                          <span class="ds-badge" :style="{ color: TASK_STATE_COLORS[task.state ?? ''] ?? '#475569' }">
                            {{ taskStateLabel(task.state) }}
                          </span>
                        </td>
                        <td>{{ task.submitTime ?? '—' }}</td>
                        <td>{{ task.startTime ?? '—' }}</td>
                        <td>{{ task.endTime ?? '—' }}</td>
                        <td>{{ task.duration ?? '—' }}</td>
                        <td>{{ task.retryTimes ?? 0 }}</td>
                        <td>{{ task.host ?? '—' }}</td>
                        <td>
                          <button
                            class="ds-btn"
                            data-ds-run-task-log
                            :data-ds-run-task-log-id="task.id"
                            @click="openLogs(task)"
                          >日志</button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div class="ds-block" data-ds-run-variables-block>
                  <strong class="ds-block-title">实例变量（只读，§10.7 D3）</strong>
                  <p v-if="!variables || !variables.globalParams.length" class="ds-hint" data-ds-run-variables-empty>暂无全局参数</p>
                  <ul v-else class="ds-vars" data-ds-run-variables>
                    <li v-for="param in variables.globalParams" :key="param.prop">
                      <code>{{ param.prop }}</code> = <code>{{ param.value }}</code>
                    </li>
                  </ul>
                </div>

                <div class="ds-block" data-ds-run-logs-block>
                  <header class="ds-logs-head">
                    <strong class="ds-block-title">任务实例日志</strong>
                    <span v-if="logTaskId !== null" class="ds-logs-target" data-ds-run-logs-target>任务 #{{ logTaskId }}</span>
                  </header>
                  <p v-if="logsLoading" class="ds-hint" data-ds-run-logs-loading>日志加载中…</p>
                  <p v-else-if="logsError" class="ds-hint" data-ds-run-logs-error>{{ logsError }}</p>
                  <p v-else-if="logTaskId === null" class="ds-hint" data-ds-run-logs-idle>点上方任务行的「日志」查看</p>
                  <p v-else-if="!logs.length" class="ds-hint" data-ds-run-logs-empty>暂无日志</p>
                  <pre v-else class="ds-logs-body" data-ds-run-logs-body>{{ logs.map((line) => `${line.lineNum}: ${line.message}`).join('\n') }}</pre>
                </div>
              </template>
            </td>
          </tr>
        </template>
      </tbody>
    </table>

    <nav v-if="total > PAGE_SIZE" class="ds-pagination" data-ds-run-pagination>
      <button class="ds-btn" :disabled="loading || pageNo <= 1" data-ds-run-previous @click="onPrevPage">上一页</button>
      <span>{{ rangeText }}</span>
      <button class="ds-btn" :disabled="loading || pageNo * PAGE_SIZE >= total" data-ds-run-next @click="onNextPage">下一页</button>
    </nav>
  </section>
</template>

<style scoped>
.ds-run{flex:1;min-height:0;display:flex;flex-direction:column;padding:16px 18px;gap:12px;overflow:auto}
.ds-run-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
.ds-run-title{margin:0;font-size:15px;font-weight:600;color:var(--text-primary, var(--text))}
.ds-run-sub{margin:4px 0 0;font-size:12.5px;color:var(--text-secondary, var(--text-2))}
.ds-run-filters{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ds-input{border:1px solid var(--border-color, var(--border));border-radius:var(--radius-sm, 6px);padding:5px 10px;font-size:12.5px;background:var(--card);color:var(--text-primary, var(--text));min-width:180px}
.ds-hint{margin:0;padding:24px 0;text-align:center;font-size:13px;color:var(--text-secondary, var(--text-2))}
.ds-table{width:100%;border-collapse:collapse;font-size:12.5px}
.ds-table th,.ds-table td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border-color, var(--border));color:var(--text-primary, var(--text));vertical-align:top}
.ds-table th{font-weight:600;color:var(--text-secondary, var(--text-2))}
.ds-name{margin-left:6px;font-weight:600}
.ds-id{margin-left:6px;color:var(--text-4, var(--border-strong));font-size:11.5px}
.ds-badge{font-weight:600}
.ds-ops{display:flex;gap:6px;flex-wrap:wrap}
.ds-btn{border:1px solid var(--border-color, var(--border));background:var(--card);color:var(--text-primary, var(--text));border-radius:var(--radius-sm, 6px);padding:3px 10px;font-size:12px;cursor:pointer}
.ds-btn:hover:not(:disabled){border-color:var(--primary-color, var(--primary));color:var(--primary-color, var(--primary))}
.ds-btn:disabled{color:var(--text-4, var(--border-strong));cursor:not-allowed}
.ds-link{border:none;background:none;padding:0;font-size:12px;color:var(--primary-color, var(--primary));cursor:pointer;margin-right:4px}
.ds-link:hover{text-decoration:underline}
.ds-detail-row > td{padding:12px 14px;background:var(--bg-secondary, var(--bg))}
.ds-block{margin-bottom:14px}
.ds-block-title{font-size:12.5px;color:var(--text-secondary, var(--text-2))}
.ds-sub-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
.ds-sub-table th,.ds-sub-table td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border-color, var(--border))}
.ds-gantt{margin-top:6px;display:flex;flex-direction:column;gap:4px}
.ds-gantt-row{display:flex;align-items:center;gap:8px}
.ds-gantt-name{width:220px;flex-shrink:0;font-size:11.5px;color:var(--text-secondary, var(--text-2));overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ds-gantt-track{position:relative;flex:1;height:14px;background:var(--bg, #f1f5f9);border-radius:3px}
.ds-gantt-bar{position:absolute;top:2px;height:10px;border-radius:2px;background:#2563eb}
.ds-gantt-success{background:#16a34a}
.ds-gantt-failure,.ds-gantt-need_fault_tolerance{background:#dc2626}
.ds-gantt-running_execution,.ds-gantt-running{background:#2563eb}
.ds-gantt-kill,.ds-gantt-pause{background:#d97706}
.ds-vars{margin:6px 0 0;padding-left:18px;font-size:12px;color:var(--text-primary, var(--text))}
.ds-vars code{color:var(--primary-color, var(--primary))}
.ds-logs-head{display:flex;align-items:center;gap:8px}
.ds-logs-target{font-size:11.5px;color:var(--text-4, var(--border-strong))}
.ds-logs-body{margin:6px 0 0;padding:8px 10px;background:#0f172a;color:#e2e8f0;border-radius:5px;font-size:12px;line-height:1.6;max-height:260px;overflow:auto;white-space:pre-wrap}
.ds-pagination{display:flex;align-items:center;gap:10px;font-size:12.5px;color:var(--text-secondary, var(--text-2))}
</style>
