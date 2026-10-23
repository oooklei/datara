<template>
  <main class="qc-task-page" aria-label="检查任务">
    <header class="qc-head">
      <div>
        <h1>检查任务</h1>
        <p>质量规则执行记录。structural 口径下行级四字段恒 0，本页只呈现结构与状态，不推断行级结果。</p>
      </div>
      <label class="qc-project">项目
        <select v-model="selected" data-project-select @change="reload">
          <option value="">请选择项目</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </label>
      <button type="button" data-refresh @click="reload">刷新</button>
    </header>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，刷新失败时列表须保留 -->
    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="busy" role="status">正在加载…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="runs.length === 0 && !error" data-empty>暂无检查任务</p>

    <table v-else-if="runs.length > 0" data-run-list>
      <thead>
        <tr><th>ID</th><th>规则</th><th>资产</th><th>状态</th><th>摘要</th><th>生成时间</th></tr>
      </thead>
      <tbody>
        <tr v-for="run in runs" :key="run.id" :data-run-id="run.id">
          <td data-run-id-cell>{{ run.id }}</td>
          <td data-rule>#{{ run.ruleId ?? '—' }}</td>
          <td data-asset>#{{ run.assetId }}</td>
          <td :data-status="run.status">{{ statusLabel(run.status) }}</td>
          <td data-summary>{{ summaryText(run) }}</td>
          <td data-generated>{{ run.generatedAt || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <p class="qc-note" role="note" data-structural-note>
      structural 口径：执行仅做结构谓词校验，行级四字段恒 0；行级采样需绑定数据源。
    </p>
  </main>
</template>

<script setup lang="ts">
/**
 * 质量五项批 A · 检查任务页（IMPL-v4-07，`/qc/task`）。
 *
 * 契约面：`governanceApi.listRuns`（quality-runs 列表）。
 * 项目上下文：同 `QualityRuleView.vue`——全局模式路由，从 `route.params.projectId`
 *   或 `route.query.projectId` 承接（「运行记录」入口携 query 跳转）；
 *   两者皆空时呈现选择器，不渲染空壳。
 *
 * structural 红线（验收 ④）：本页**不**呈现 `checkedRows/successRows/failedRows/skippedRows`
 *   行级计数，只呈现后端 `status` 与 `summary`（engine/message/issues）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  QUALITY_STRUCTURAL_ONLY,
  governanceApi,
  type QualityRunRecord,
  type QualityRunStatus,
} from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()

const projects = ref<ProjectSummary[]>([])
const selected = ref('')
const runs = ref<QualityRunRecord[]>([])
const busy = ref(false)
const error = ref('')

/** 项目上下文：route 参数优先，其次 query（跨页携带）。 */
const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const projectId = computed<number | null>(() => {
  const fromRoute = routeProjectId.value
  if (fromRoute !== null) return fromRoute
  const n = Number(selected.value)
  return selected.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})

const STATUS_LABEL: Record<QualityRunStatus, string> = {
  queued: '排队中',
  running: '执行中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
}
const statusLabel = (s: QualityRunStatus): string => STATUS_LABEL[s] ?? s

/** structural 摘要文案：engine + message + 命中禁用词；不含行级计数。 */
const summaryText = (run: QualityRunRecord): string => {
  const issues = run.summary.issues.length ? `；命中禁用词：${run.summary.issues.join('、')}` : ''
  return `${run.summary.engine}：${run.summary.message}${issues}`
}

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

async function loadProjects(): Promise<void> {
  try {
    const page = await listProjects()
    projects.value = page.list
  } catch (e) {
    error.value = message(e)
  }
}

async function reload(): Promise<void> {
  if (projectId.value === null) {
    runs.value = []
    return
  }
  busy.value = true
  error.value = ''
  try {
    const page = await governanceApi.listRuns(projectId.value)
    runs.value = page.list
  } catch (e) {
    error.value = message(e)
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  if (routeProjectId.value !== null) selected.value = String(routeProjectId.value)
  await loadProjects()
  await reload()
})
</script>

<style scoped>
.qc-task-page{max-width:1180px;margin:auto;padding:32px 24px;color:#172033}
.qc-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.qc-head h1{margin:0}
.qc-head p{margin:4px 0 0;color:#64748b;flex-basis:100%}
.qc-project{display:flex;align-items:center;gap:8px;margin-left:auto}
.qc-project select{padding:7px 10px;min-width:180px}
button{cursor:pointer;padding:7px 12px}
table{width:100%;border-collapse:collapse;background:#fff;margin-top:8px}
th,td{text-align:left;padding:11px;border-bottom:1px solid #e2e8f0;vertical-align:top}
.qc-note{margin-top:16px;color:#475569;font-size:13px}
</style>
