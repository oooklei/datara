<template>
  <main class="pg" aria-label="检查任务">
    <header class="pg-head">
      <h1 class="sec-head">检查任务</h1>
      <p class="pg-desc">质量规则执行记录。数据检查运行显示实查行数；未绑定连接的结构校验不产生行级结论。</p>
    </header>

    <div class="toolbar">
      <button type="button" class="op-btn" data-refresh :disabled="busy" @click="reload">刷新</button>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">共 {{ total }} 条</span>
    </div>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，刷新失败时列表须保留 -->
    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="busy" @click="reload">重试</button>
    </div>

    <div v-if="busy" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:28%"></div>
      <div class="skeleton sk-row" style="width:66%"></div>
      <div class="skeleton sk-row" style="width:48%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载检查任务。</div>
    </div>

    <!-- 空态须让位于错误态：加载失败时不得呈现「暂无数据」空壳 -->
    <div v-else-if="runs.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">暂无检查任务</div>
      <div class="e-hint">当前项目下还没有质量规则执行记录。</div>
    </div>

    <div v-else-if="runs.length > 0" class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">执行记录</span>
        <span class="pill info">{{ filteredRuns.length }}</span>
        <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索 ID、规则、资产或状态">
        <span class="spacer"></span>
      </div>
      <table class="tbl" data-run-list>
        <thead>
          <tr><th>ID</th><th>规则</th><th>资产</th><th>状态</th><th>摘要</th><th>生成时间</th></tr>
        </thead>
        <tbody>
          <tr v-for="run in filteredRuns" :key="run.id" :data-run-id="run.id">
            <td data-run-id-cell><span class="code-chip">#{{ run.id }}</span></td>
            <td data-rule><span class="code-chip">#{{ run.ruleId ?? '—' }}</span></td>
            <td data-asset><span class="code-chip">#{{ run.assetId }}</span></td>
            <td><span class="st" :class="statusClass(run.status)" :data-status="run.status"><span class="dot"></span>{{ statusLabel(run.status) }}</span></td>
            <td data-summary>{{ summaryText(run) }}</td>
            <td data-generated>{{ run.generatedAt || '—' }}</td>
          </tr>
          <tr v-if="filteredRuns.length === 0"><td colspan="6">无匹配记录</td></tr>
        </tbody>
      </table>
    </div>

    <p v-if="projectId !== null" class="lock-tip" role="note" data-structural-note>
      仅 DBX 运行记录包含实查行数；结构校验记录的计数为 0。
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
 *
 * 样式范式：复用全局设计系统（`.pg`/`.panel`/`.tbl`/`.st`/`.code-chip` + `var(--*)` 令牌），
 *   与旧前端 datara-web QcTaskView 的 `.card.panel` + `.tbl-toolbar` + `table.tbl` 范式对齐。
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
const filterKeyword = ref('')
/** D13 列表搜索：前端过滤 id/ruleId/assetId/status，不触发后端。 */
const filteredRuns = computed(() => {
  const keyword = filterKeyword.value.toLowerCase()
  if (keyword === '') return runs.value
  return runs.value.filter((run) =>
    String(run.id).includes(keyword) ||
    String(run.ruleId ?? '').includes(keyword) ||
    String(run.assetId).includes(keyword) ||
    run.status.toLowerCase().includes(keyword))
})
const total = ref(0)
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
const STATUS_CLASS: Record<QualityRunStatus, string> = {
  queued: 'st-blue',
  running: 'st-blue',
  succeeded: 'st-green',
  failed: 'st-red',
  cancelled: 'st-gray',
}
const statusClass = (s: QualityRunStatus): string => STATUS_CLASS[s] ?? 'st-gray'

/** 结构校验不推断行级结果；DBX 运行使用持久化计数。 */
const summaryText = (run: QualityRunRecord): string => {
  const issues = run.summary.issues.length ? `；命中禁用词：${run.summary.issues.map(item => typeof item === 'string' ? item : item.code).join('、')}` : ''
  const counts = run.summary.engine === 'dbx'
    ? `；检查 ${run.checkedRows} 行，通过 ${run.successRows} 行，不合规则 ${run.failedRows} 行`
    : ''
  return `${run.summary.engine}：${run.summary.message}${issues}${counts}`
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
    total.value = 0
    return
  }
  busy.value = true
  error.value = ''
  try {
    const page = await governanceApi.listRuns(projectId.value)
    runs.value = page.list
    total.value = page.total
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
