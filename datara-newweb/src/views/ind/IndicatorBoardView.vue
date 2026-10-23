<template>
  <main class="ind-page" aria-label="指标看板">
    <header class="ind-head">
      <div>
        <h1>指标看板</h1>
        <p>指标目录的看板视图（当前无指标结果端点，按定义卡片呈现）。</p>
      </div>
      <div class="ind-actions">
        <label>项目
          <select v-model="selectedProject" data-project-select @change="reload">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
      </div>
    </header>

    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="loading" role="status">加载中…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="page.list.length === 0" data-empty>暂无指标（请先在指标目录创建）</p>

    <section v-else class="board" data-ind-board>
      <article v-for="m in page.list" :key="m.id" class="card">
        <h2>{{ m.name }}</h2>
        <p class="code">{{ m.code }}</p>
        <code>{{ m.formula }}</code>
        <p class="status" :data-status="m.status">{{ m.status }}</p>
      </article>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type MetricPage } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const page = ref<MetricPage>({ total: 0, list: [] })
const loading = ref(false)
const error = ref('')

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

onMounted(async () => {
  try {
    const p = await listProjects()
    projects.value = p.list
    if (routeProjectId.value !== null) selectedProject.value = String(routeProjectId.value)
    if (selectedProject.value) await reload()
  } catch (e) { error.value = message(e) }
})

async function reload(): Promise<void> {
  if (projectId.value === null) { page.value = { total: 0, list: [] }; return }
  loading.value = true
  error.value = ''
  try {
    page.value = await governanceApi.listMetrics(projectId.value)
  } catch (e) { error.value = message(e) } finally { loading.value = false }
}
</script>

<style scoped>
.ind-page{max-width:1100px;margin:auto;padding:24px}
.ind-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between}
.ind-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.board{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-top:16px}
.card{border:1px solid #e2e8f0;border-radius:6px;padding:12px;display:grid;gap:6px}
.code{color:#475569;font-size:12px}
.status{text-transform:uppercase;font-size:12px;color:#64748b}
.status[data-status='active']{color:#15803d}
</style>
