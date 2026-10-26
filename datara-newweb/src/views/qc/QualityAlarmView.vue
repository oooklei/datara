<template>
  <main class="pg" aria-label="质量告警">
    <header class="pg-head">
      <h1 class="sec-head">质量告警</h1>
      <p class="pg-desc">按失败运行聚合告警列表（告警中心独立建模前置口径）。本页只呈现结构与状态，不推断行级结果。</p>
    </header>

    <div class="toolbar">
      <label class="field"><span>项目</span>
        <select v-model="selectedProject" class="kw" data-project-select @change="reload">
          <option value="">请选择项目</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </label>
      <button type="button" class="op-btn" data-refresh :disabled="loading" @click="reload">刷新</button>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">告警 {{ alarms.length }} / 共 {{ runs.length }}</span>
    </div>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，刷新失败时列表须保留 -->
    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading" @click="reload">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:28%"></div>
      <div class="skeleton sk-row" style="width:66%"></div>
      <div class="skeleton sk-row" style="width:48%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载告警列表。</div>
    </div>

    <!-- 空态须让位于错误态：加载失败时不得呈现「暂无数据」空壳 -->
    <div v-else-if="alarms.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">暂无告警</div>
      <div class="e-hint">当前项目下没有失败的质量运行。</div>
    </div>

    <div v-else-if="alarms.length > 0" class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">告警记录</span>
        <span class="pill err">{{ alarms.length }}</span>
        <span class="spacer"></span>
      </div>
      <ul class="node-list" data-alarm-list>
        <li v-for="a in alarms" :key="a.id">
          <strong>运行 #{{ a.id }}</strong>
          <span>资产 #{{ a.assetId }}</span>
          <span>{{ hitText(a) }}</span>
          <span class="mono">{{ a.generatedAt || '—' }}</span>
        </li>
      </ul>
    </div>

    <p v-if="projectId !== null" class="lock-tip" role="note" data-structural-note>
      structural 口径：执行仅做结构谓词校验，行级四字段恒 0；本页不呈现行级计数。
    </p>
  </main>
</template>

<script setup lang="ts">
/**
 * 质量五项批 A · 质量告警页（IMPL-v4-10，`/qc/alarm`）。
 *
 * 契约面：`governanceApi.listRuns`（quality-runs 列表）+ 前端按 `status === 'failed'` 过滤。
 * 项目上下文：同 `QualityRuleView.vue`——全局模式路由，从 `route.params.projectId`
 *   或 `route.query.projectId` 承接；两者皆空时呈现选择器，不渲染空壳。
 *
 * structural 红线（验收 ④）：本页**不**呈现行级四字段计数，只呈现后端 `status` 与 `summary`。
 *
 * 样式范式：复用全局设计系统（`.pg`/`.panel`/`.node-list`/`.mono` + `var(--*)` 令牌），
 *   与旧前端 datara-web QcAlarmView 的 `.card.panel` + 告警列表范式对齐。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type QualityRunRecord } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()

const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const runs = ref<QualityRunRecord[]>([])
const loading = ref(false)
const error = ref('')

/** 项目上下文：route 参数优先，其次本地选择器。 */
const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const projectId = computed<number | null>(() => {
  const fromRoute = routeProjectId.value
  if (fromRoute !== null) return fromRoute
  const n = Number(selectedProject.value)
  return selectedProject.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const alarms = computed(() => runs.value.filter((r) => r.status === 'failed'))

/** 命中项文案：issues 优先，回落 summary.message；不含行级计数。 */
const hitText = (run: QualityRunRecord): string =>
  run.summary.issues.length ? run.summary.issues.join('、') : run.summary.message

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
  loading.value = true
  error.value = ''
  try {
    const page = await governanceApi.listRuns(projectId.value, 1, 100)
    runs.value = page.list
  } catch (e) {
    error.value = message(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (routeProjectId.value !== null) selectedProject.value = String(routeProjectId.value)
  await loadProjects()
  await reload()
})
</script>
