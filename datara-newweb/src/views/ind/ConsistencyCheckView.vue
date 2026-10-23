<template>
  <main class="ind-page" aria-label="一致性检查">
    <header class="ind-head">
      <div>
        <h1>一致性检查</h1>
        <p>按标准执行结构校验（当前复用 standards/check；跨源一致性端点候后端补齐）。</p>
      </div>
      <div class="ind-actions">
        <label>项目
          <select v-model="selectedProject" data-project-select @change="loadStandards">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <label>标准
          <select v-model="selectedStd" data-standard-select :disabled="standards.length === 0">
            <option value="">请选择标准</option>
            <option v-for="s in standards" :key="s.id" :value="String(s.id)">{{ s.code }} - {{ s.name }}</option>
          </select>
        </label>
        <button type="button" :disabled="projectId === null || selectedStd === ''" @click="runCheck">执行检查</button>
      </div>
    </header>

    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="loading" role="status">加载中…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>

    <template v-if="projectId !== null">
      <p v-if="!result" data-pending>选择标准后执行检查。</p>
      <ul v-else-if="results.length === 0" data-empty>检查无返回</ul>
      <table v-else data-consistency-result>
        <thead><tr><th>标准</th><th>编码</th><th>结果</th><th>引擎</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="r in results" :key="r.standardId">
            <td>#{{ r.standardId }}</td>
            <td>{{ r.code }}</td>
            <td>{{ r.passed ? '通过' : '未通过' }}</td>
            <td>{{ r.engine }}</td>
            <td>{{ r.checkedAt || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  governanceApi,
  type StandardCheckResult,
  type StandardDefinition,
} from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const standards = ref<StandardDefinition[]>([])
const selectedStd = ref('')
const results = ref<StandardCheckResult[]>([])
const result = ref<StandardCheckResult[] | null>(null)
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
    if (selectedProject.value) await loadStandards()
  } catch (e) { error.value = message(e) }
})

async function loadStandards(): Promise<void> {
  selectedStd.value = ''
  result.value = null
  results.value = []
  if (projectId.value === null) { standards.value = []; return }
  loading.value = true
  error.value = ''
  try {
    const page = await governanceApi.listStandards(projectId.value)
    standards.value = page.list
  } catch (e) { error.value = message(e) } finally { loading.value = false }
}

async function runCheck(): Promise<void> {
  if (projectId.value === null || selectedStd.value === '') return
  error.value = ''
  try {
    results.value = await governanceApi.checkStandard(projectId.value, { standardId: Number(selectedStd.value) })
    result.value = results.value
  } catch (e) { error.value = message(e) }
}
</script>

<style scoped>
.ind-page{max-width:1100px;margin:auto;padding:24px}
.ind-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between}
.ind-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
table{width:100%;border-collapse:collapse;margin-top:16px}
th,td{border-bottom:1px solid #e2e8f0;padding:6px 8px;text-align:left;font-size:13px}
</style>
