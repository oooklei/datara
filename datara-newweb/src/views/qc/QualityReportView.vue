<template>
  <main class="pg" aria-label="质量报告">
    <header class="pg-head">
      <h1 class="sec-head">质量报告</h1>
      <p class="pg-desc">质量运行汇总。聚合完全由前端按运行记录状态计算，不引入新后端口径。</p>
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
      <span v-if="projectId !== null" class="hint">统计口径：运行记录状态</span>
    </div>

    <!-- 错误横幅独立于内容态：加载失败时无数据可渲染，刷新失败时统计须保留 -->
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
      <div class="e-hint">在上方下拉框选择项目后，即可查看质量运行汇总。</div>
    </div>

    <div v-else class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">运行汇总</span>
        <span class="pill info">{{ page.total }}</span>
        <span class="spacer"></span>
      </div>
      <section class="stat-line" data-report-cards>
        <div class="stat-mini">
          <div class="k">总运行数</div>
          <div class="v" data-metric="total">{{ page.total }}</div>
        </div>
        <div class="stat-mini">
          <div class="k">成功</div>
          <div class="v" data-metric="succeeded">{{ succeeded }}</div>
        </div>
        <div class="stat-mini">
          <div class="k">失败</div>
          <div class="v" data-metric="failed">{{ failed }}</div>
        </div>
        <div class="stat-mini">
          <div class="k">队列 / 运行中</div>
          <div class="v" data-metric="running">{{ running }}</div>
        </div>
      </section>
    </div>

    <!-- 空态须让位于错误态：加载失败时不得呈现「暂无数据」空壳 -->
    <div v-if="projectId !== null && !loading && !error && page.list.length === 0" class="panel empty" data-empty>
      <div class="e-title">暂无运行记录</div>
      <div class="e-hint">当前项目下还没有质量规则执行记录。</div>
    </div>

    <p v-if="projectId !== null" class="lock-tip" role="note" data-structural-note>
      structural 口径：执行仅做结构谓词校验，行级四字段恒 0；本页不呈现行级计数。
    </p>
  </main>
</template>

<script setup lang="ts">
/**
 * 质量五项批 A · 质量报告页（IMPL-v4-09，`/qc/report`）。
 *
 * 契约面：`governanceApi.listRuns`（quality-runs 列表）+ 前端按状态聚合四类计数。
 * 项目上下文：同 `QualityRuleView.vue`——全局模式路由，从 `route.params.projectId`
 *   或 `route.query.projectId` 承接；两者皆空时呈现选择器，不渲染空壳。
 *
 * structural 红线（验收 ④）：本页**不**呈现行级四字段计数，聚合仅基于运行 `status`。
 *
 * 样式范式：复用全局设计系统（`.pg`/`.panel`/`.stat-line`/`.stat-mini` + `var(--*)` 令牌），
 *   与旧前端 datara-web QcReportView 的 `.card.panel` + 统计卡范式对齐。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type QualityRunPage } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()

const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const page = ref<QualityRunPage>({ total: 0, list: [] })
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
const succeeded = computed(() => page.value.list.filter((r) => r.status === 'succeeded').length)
const failed = computed(() => page.value.list.filter((r) => r.status === 'failed').length)
const running = computed(
  () => page.value.list.filter((r) => r.status === 'queued' || r.status === 'running').length,
)

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

async function loadProjects(): Promise<void> {
  try {
    const page2 = await listProjects()
    projects.value = page2.list
  } catch (e) {
    error.value = message(e)
  }
}

async function reload(): Promise<void> {
  if (projectId.value === null) {
    page.value = { total: 0, list: [] }
    return
  }
  loading.value = true
  error.value = ''
  try {
    page.value = await governanceApi.listRuns(projectId.value, 1, 100)
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
