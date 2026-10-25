<template>
  <main class="quality-page" :data-quality-view="kind">
    <header class="page-head">
      <div>
        <h1>{{ title }}</h1>
        <p>{{ description }}</p>
      </div>
      <label>项目
        <select v-model="selectedProject" data-project-select @change="reload">
          <option value="">请选择项目</option>
          <option v-for="project in projects" :key="project.id" :value="String(project.id)">{{ project.name }}</option>
        </select>
      </label>
      <label v-if="kind === 'exceptions'">状态
        <input v-model.trim="status" data-status-filter placeholder="全部状态">
      </label>
      <button type="button" data-refresh @click="reload">刷新</button>
    </header>

    <p v-if="error" role="alert" class="error" data-error>{{ error }}</p>
    <p v-else-if="busy" role="status">正在加载…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="rows.length === 0" data-empty>暂无数据</p>

    <table v-else-if="kind === 'exceptions'" data-quality-table>
      <thead><tr><th>ID</th><th>目标</th><th>状态</th><th>命中数</th><th>样例 SQL</th><th>处理信息</th></tr></thead>
      <tbody><tr v-for="row in exceptionRows" :key="row.id">
        <td>{{ row.id }}</td><td>{{ row.target }}</td><td>{{ row.status }}</td><td>{{ row.hitCount }}</td>
        <td><code>{{ row.sampleSql || '—' }}</code></td><td>{{ row.fixNote || row.handledBy || '—' }}</td>
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
      <thead><tr><th>ID</th><th>名称</th><th>范围</th><th>指标</th><th>条件</th><th>启用</th><th>最近触发</th></tr></thead>
      <tbody><tr v-for="row in alarmRows" :key="row.id">
        <td>{{ row.id }}</td><td>{{ row.name }}</td><td>{{ row.scope }}</td><td>{{ row.metric }}</td>
        <td>{{ row.operator }} {{ row.threshold }}</td><td>{{ row.enabled ? '是' : '否' }}</td><td>{{ row.lastFiredAt || '—' }}</td>
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
const error = ref('')

const kind = computed(() => props.kind)
const title = computed(() => ({ exceptions: '异常核查', reports: '质量报告', alarms: '质量告警' })[kind.value])
const description = computed(() => ({
  exceptions: '只读核查质量异常、命中样例与处理状态。',
  reports: '查看已生成的质量报告及其统计内容。',
  alarms: '查看质量告警策略、阈值与最近触发时间。',
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

async function reload() {
  if (projectId.value === null) { rows.value = []; total.value = 0; return }
  busy.value = true
  error.value = ''
  try {
    const result = kind.value === 'exceptions'
      ? await governanceApi.listExceptions(projectId.value, page.value, pageSize, status.value || undefined)
      : kind.value === 'reports'
        ? await governanceApi.listReports(projectId.value, page.value, pageSize)
        : await governanceApi.listAlarmPolicies(projectId.value, page.value, pageSize)
    rows.value = result.list
    total.value = result.total
  } catch (cause) {
    error.value = message(cause)
    rows.value = []
    total.value = 0
  } finally {
    busy.value = false
  }
}

function previous() { page.value = Math.max(1, page.value - 1); void reload() }
function next() { page.value += 1; void reload() }

watch(() => props.kind, () => { page.value = 1; rows.value = []; void reload() })
onMounted(async () => {
  try {
    const result = await listProjects()
    projects.value = result.list
    const queryId = Number(route.query.projectId)
    const initial = projects.value.find((project) => project.id === queryId) ?? projects.value[0]
    if (initial) selectedProject.value = String(initial.id)
    await reload()
  } catch (cause) {
    error.value = message(cause)
  }
})
</script>

<style scoped>
.quality-page{max-width:1280px;margin:auto;padding:32px 24px;color:#172033}.page-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}.page-head>div{margin-right:auto}.page-head h1{margin:0}.page-head p{margin:6px 0 0;color:#64748b}.page-head label{display:flex;align-items:center;gap:8px}.page-head select,.page-head input,button{padding:7px 10px}table{width:100%;border-collapse:collapse;background:#fff;margin-top:18px}th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0;vertical-align:top}code{white-space:pre-wrap;word-break:break-word}.error{color:#b91c1c}.pager{display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-top:16px}
</style>
