<template>
  <main class="quality-page" :data-quality-view="kind">
    <header class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <label v-if="kind === 'exceptions'">状态
        <input v-model.trim="status" data-status-filter placeholder="全部状态">
      </label>
      <button type="button" data-refresh @click="reload">刷新</button>
    </header>

    <section v-if="projectId !== null && kind === 'reports'" class="write-panel" data-quality-write="reports">
      <label>报告标题<input v-model.trim="reportTitle" data-report-title placeholder="例如：质量日报"></label>
      <label>范围<input v-model.trim="reportScope" data-report-scope></label>
      <label>周期<input v-model.trim="reportPeriod" data-report-period></label>
      <button type="button" data-report-create :disabled="writing || !reportTitle" @click="generateReport">生成报告</button>
    </section>
    <section v-if="projectId !== null && kind === 'alarms'" class="write-panel" data-quality-write="alarms">
      <label>策略名称<input v-model.trim="alarmName" data-alarm-name placeholder="例如：失败行告警"></label>
      <label>指标<select v-model="alarmMetric" data-alarm-metric><option value="failed_rows">失败行</option><option value="failure_rate">失败率</option><option value="score">质量评分</option></select></label>
      <label>条件<select v-model="alarmOperator" data-alarm-operator><option>&gt;</option><option>&gt;=</option><option>&lt;</option><option>&lt;=</option><option>==</option></select></label>
      <label>阈值<input v-model.number="alarmThreshold" type="number" data-alarm-threshold></label>
      <button type="button" data-alarm-create :disabled="writing || !alarmName" @click="addAlarmPolicy">新建策略</button>
    </section>

    <p v-if="error" role="alert" class="error" data-error>{{ error }}</p>
    <p v-else-if="busy" role="status">正在加载…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="rows.length === 0" data-empty>暂无数据</p>

    <table v-else-if="kind === 'exceptions'" data-quality-table>
      <thead><tr><th>ID</th><th>目标</th><th>状态</th><th>命中数</th><th>样例 SQL</th><th>处理信息</th><th>操作</th></tr></thead>
      <tbody><tr v-for="row in exceptionRows" :key="row.id">
        <td>{{ row.id }}</td><td>{{ row.target }}</td><td>{{ row.status }}</td><td>{{ row.hitCount }}</td>
        <td><code>{{ row.sampleSql || '—' }}</code></td><td>{{ row.fixNote || row.handledBy || '—' }}</td>
        <td><template v-if="row.status === 'open'">
          <input v-model.trim="exceptionNotes[row.id]" :data-exception-note="row.id" placeholder="处置说明">
          <button type="button" :data-exception-dispose="row.id" :disabled="writing || !exceptionNotes[row.id]" @click="dispose(row)">标记解决</button>
        </template><span v-else>已处置</span></td>
      </tr></tbody>
    </table>

    <table v-else-if="kind === 'reports'" data-quality-table>
      <thead><tr><th>ID</th><th>标题</th><th>范围</th><th>周期</th><th>内容</th><th>创建人</th></tr></thead>
      <tbody><tr v-for="row in reportRows" :key="row.id">
        <td>{{ row.id }}</td><td>{{ row.title }}</td><td>{{ row.scope }}</td><td>{{ row.period }}</td>
        <td><code>{{ compactJson(row.content) }}</code></td><td>{{ row.createdBy }}</td>
      </tr></tbody>
    </table>

    <table v-else data-quality-table>
      <thead><tr><th>ID</th><th>名称</th><th>范围</th><th>指标</th><th>条件</th><th>启用</th><th>最近触发</th><th>操作</th></tr></thead>
      <tbody><tr v-for="row in alarmRows" :key="row.id">
        <td>{{ row.id }}</td><td>{{ row.name }}</td><td>{{ row.scope }}</td><td>{{ row.metric }}</td>
        <td>{{ row.operator }} {{ row.threshold }}</td><td>{{ row.enabled ? '是' : '否' }}</td><td>{{ row.lastFiredAt || '—' }}</td>
        <td><button type="button" :data-alarm-toggle="row.id" :disabled="writing" @click="toggleAlarm(row)">{{ row.enabled ? '停用' : '启用' }}</button></td>
      </tr></tbody>
    </table>

    <footer v-if="total > pageSize" class="pager">
      <button type="button" :disabled="page === 1" @click="previous">上一页</button>
      <span>第 {{ page }} 页，共 {{ total }} 条</span>
      <button type="button" :disabled="page * pageSize >= total" @click="next">下一页</button>
    </footer>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type QualityAlarmPolicyRecord, type QualityExceptionRecord, type QualityReportRecord } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

type QualityViewKind = 'exceptions' | 'reports' | 'alarms'
const props = defineProps<{ kind: QualityViewKind }>()
const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const status = ref('')
const page = ref(1)
const pageSize = 50
const total = ref(0)
const rows = ref<Array<QualityExceptionRecord | QualityReportRecord | QualityAlarmPolicyRecord>>([])
const busy = ref(false)
const writing = ref(false)
const error = ref('')
const exceptionNotes = ref<Record<number, string>>({})
const reportTitle = ref('')
const reportScope = ref('project')
const reportPeriod = ref('daily')
const alarmName = ref('')
const alarmMetric = ref<'failed_rows' | 'failure_rate' | 'score'>('failed_rows')
const alarmOperator = ref<'>' | '>=' | '<' | '<=' | '=='>('>')
const alarmThreshold = ref(0)

const kind = computed(() => props.kind)
const title = computed(() => ({ exceptions: '异常核查', reports: '质量报告', alarms: '质量告警' })[kind.value])
const description = computed(() => ({
  exceptions: '定位质量异常、核查命中样例并记录处置结果。',
  reports: '按项目运行结果生成并查阅质量报告。',
  alarms: '配置质量告警策略、阈值和启停状态。',
})[kind.value])
const projectId = computed<number | null>(() => {
  const value = Number(selectedProject.value)
  return selectedProject.value !== '' && Number.isInteger(value) && value > 0 ? value : null
})
const exceptionRows = computed(() => rows.value as QualityExceptionRecord[])
const reportRows = computed(() => rows.value as QualityReportRecord[])
const alarmRows = computed(() => rows.value as QualityAlarmPolicyRecord[])

const compactJson = (value: Record<string, unknown>) => JSON.stringify(value)
const message = (cause: unknown) => cause instanceof Error ? cause.message : String(cause)

let requestSeq = 0
async function reload() {
  const seq = ++requestSeq
  if (projectId.value === null) {
    rows.value = []
    total.value = 0
    error.value = ''
    busy.value = false
    return
  }
  busy.value = true
  error.value = ''
  try {
    const result = kind.value === 'exceptions'
      ? await governanceApi.listExceptions(projectId.value, page.value, pageSize, status.value || undefined)
      : kind.value === 'reports'
        ? await governanceApi.listReports(projectId.value, page.value, pageSize)
        : await governanceApi.listAlarmPolicies(projectId.value, page.value, pageSize)
    if (seq !== requestSeq) return
    rows.value = result.list
    total.value = result.total
  } catch (cause) {
    if (seq !== requestSeq) return
    error.value = message(cause)
    rows.value = []
    total.value = 0
  } finally {
    if (seq === requestSeq) busy.value = false
  }
}

function previous() { page.value = Math.max(1, page.value - 1); void reload() }
function next() { page.value += 1; void reload() }
function changeProject() { page.value = 1; void reload() }

async function runWrite(action: () => Promise<unknown>) {
  if (writing.value) return
  writing.value = true
  error.value = ''
  try { await action(); await reload() }
  catch (cause) { error.value = message(cause) }
  finally { writing.value = false }
}

function dispose(row: QualityExceptionRecord) {
  const fixNote = (exceptionNotes.value[row.id] ?? '').trim()
  if (projectId.value === null || !fixNote) return
  void runWrite(() => governanceApi.disposeException(projectId.value!, row.id, { status: 'resolved', fixNote }))
}

function generateReport() {
  if (projectId.value === null || !reportTitle.value.trim()) return
  void runWrite(async () => {
    await governanceApi.createReport(projectId.value!, {
      title: reportTitle.value.trim(), scope: reportScope.value.trim() || 'project',
      period: reportPeriod.value.trim() || 'manual',
    })
    reportTitle.value = ''
  })
}

function addAlarmPolicy() {
  if (projectId.value === null || !alarmName.value.trim()) return
  void runWrite(async () => {
    await governanceApi.createAlarmPolicy(projectId.value!, {
      name: alarmName.value.trim(), scope: 'project', metric: alarmMetric.value,
      operator: alarmOperator.value, threshold: alarmThreshold.value, enabled: true,
    })
    alarmName.value = ''
  })
}

function toggleAlarm(row: QualityAlarmPolicyRecord) {
  if (projectId.value === null) return
  void runWrite(() => governanceApi.setAlarmPolicyEnabled(projectId.value!, row.id, !row.enabled))
}

watch(() => props.kind, () => { page.value = 1; rows.value = []; void reload() })
onMounted(async () => {
  try {
    const result = await listProjects()
    projects.value = result.list
    const parseProjectId = (raw: unknown): number | null => {
      const value = Array.isArray(raw) ? raw[0] : raw
      const id = Number(value)
      return value !== undefined && value !== '' && Number.isInteger(id) && id > 0 ? id : null
    }
    const requestedId = parseProjectId(route.params.projectId) ?? parseProjectId(route.query.projectId)
    const initial = projects.value.find((project) => project.id === requestedId) ?? projects.value[0]
    if (initial) selectedProject.value = String(initial.id)
    await reload()
  } catch (cause) {
    error.value = message(cause)
  }
})
</script>

<style scoped>
.quality-page{max-width:1280px;margin:auto;padding:32px 24px;color:var(--text)}.page-head,.write-panel{display:flex;align-items:center;gap:16px;flex-wrap:wrap}.page-head>div{margin-right:auto}.page-head h1{margin:0}.page-head p{margin:6px 0 0;color:var(--text-2)}.page-head label,.write-panel label{display:flex;align-items:center;gap:8px}.page-head select,.page-head input,.write-panel select,.write-panel input,button{padding:7px 10px}.write-panel{margin-top:16px;padding:14px;background:var(--card);border:1px solid var(--border);border-radius:8px}table{width:100%;border-collapse:collapse;background:var(--card);margin-top:18px}th,td{text-align:left;padding:11px;border-bottom:1px solid var(--border);vertical-align:top}td input{max-width:160px;margin-right:6px;padding:6px}code{white-space:pre-wrap;word-break:break-word}.error{color:var(--danger)}.pager{display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-top:16px}
</style>
