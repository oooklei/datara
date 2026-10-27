<template>
  <main class="pg" aria-label="访问审计">
    <header class="pg-head">
      <h1 class="sec-head">访问审计</h1>
      <p class="pg-desc">项目域审计事件（projects/{id}/audit，倒序）。仅呈现后端返回的审计记录，不本地伪造事件。</p>
    </header>

    <div class="toolbar">
      <button type="button" class="op-btn" data-refresh :disabled="loading" @click="reload">刷新</button>
      <span class="spacer"></span>
      <span v-if="projectId !== null" class="hint">共 {{ page.total }} 条</span>
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
      <div class="e-hint">在上方下拉框选择项目后，即可加载审计事件。</div>
    </div>

    <!-- 空态须让位于错误态：加载失败时不得呈现「暂无数据」空壳 -->
    <div v-else-if="page.list.length === 0 && !error" class="panel empty" data-empty>
      <div class="e-title">暂无审计事件</div>
      <div class="e-hint">当前项目下还没有可展示的审计记录。</div>
    </div>

    <div v-else-if="page.list.length > 0" class="panel">
      <div class="tbl-toolbar">
        <span class="sec-head">审计事件</span>
        <span class="pill info">{{ page.total }}</span>
        <span class="spacer"></span>
      </div>
      <table class="tbl" data-audit-list>
        <thead>
          <tr><th>时间</th><th>操作者</th><th>动作</th><th>资源</th><th>请求 ID</th></tr>
        </thead>
        <tbody>
          <tr v-for="e in page.list" :key="e.id">
            <td>{{ e.generatedAt || '—' }}</td>
            <td><span class="code-chip">#{{ e.actorId }}</span></td>
            <td>{{ e.action }}</td>
            <td>{{ e.resourceType }} / {{ e.resourceId || '—' }}</td>
            <td><code class="mono">{{ e.requestId || '—' }}</code></td>
          </tr>
        </tbody>
      </table>
    </div>
  </main>
</template>

<script setup lang="ts">
/**
 * 系统管理组 · 访问审计页（IMPL-v4-xx，`/sec/audit`）。
 *
 * 契约面：`governanceApi.listAudit`（项目域审计事件，倒序）。
 * 项目上下文：同 `QualityRuleView.vue`——全局模式路由，从 `route.params.projectId`
 *   或 `route.query.projectId` 承接；两者皆空时呈现选择器，不渲染空壳。
 *
 * 样式范式：复用全局设计系统（`.pg`/`.panel`/`.tbl-toolbar`/`.tbl`/`.code-chip`/`.mono`
 *   + `var(--*)` 令牌），与旧前端 datara-web SecAuditView 的 `.card.panel` + `table.tbl` 范式对齐。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type AuditEventPage } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()

const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const page = ref<AuditEventPage>({ total: 0, list: [] })
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
    page.value = await governanceApi.listAudit(projectId.value)
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
