<template>
  <main class="ind-page" aria-label="指标目录">
    <header class="ind-head">
      <div>
        <h1>指标目录</h1>
        <p>语义指标定义（governance metrics）。</p>
      </div>
      <div class="ind-actions">
        <label>项目
          <select v-model="selectedProject" data-project-select @change="reload">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <button type="button" :disabled="projectId === null" @click="openCreate">新建指标</button>
      </div>
    </header>

    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="loading" role="status">加载中…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="page.list.length === 0" data-empty>暂无指标</p>

    <table v-else data-ind-list>
      <thead><tr><th>编码</th><th>名称</th><th>公式</th><th>状态</th><th>更新时间</th></tr></thead>
      <tbody>
        <tr v-for="m in page.list" :key="m.id">
          <td>{{ m.code }}</td>
          <td>{{ m.name }}</td>
          <td><code>{{ m.formula }}</code></td>
          <td>{{ m.status }}</td>
          <td>{{ m.updatedAt || m.createdAt || '—' }}</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="mask" @click.self="showCreate = false">
      <form role="dialog" aria-label="新建指标" @submit.prevent="save">
        <h2>新建指标</h2>
        <label>编码<input v-model.trim="form.code" required></label>
        <label>名称<input v-model.trim="form.name" required></label>
        <label>公式<textarea v-model.trim="form.formula" required rows="3"></textarea></label>
        <label>描述<input v-model="form.description"></label>
        <label>状态
          <select v-model="form.status">
            <option value="draft">draft</option>
            <option value="active">active</option>
            <option value="retired">retired</option>
          </select>
        </label>
        <footer>
          <button type="button" @click="showCreate = false">取消</button>
          <button type="submit">保存</button>
        </footer>
      </form>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type DefinitionStatus, type MetricPage } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const page = ref<MetricPage>({ total: 0, list: [] })
const loading = ref(false)
const error = ref('')
const showCreate = ref(false)
const form = reactive({
  code: '',
  name: '',
  formula: '',
  description: '',
  status: 'draft' as DefinitionStatus,
})

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

function openCreate(): void {
  Object.assign(form, { code: '', name: '', formula: '', description: '', status: 'draft' })
  showCreate.value = true
}

async function save(): Promise<void> {
  if (projectId.value === null) return
  error.value = ''
  try {
    await governanceApi.createMetric(projectId.value, { ...form })
    showCreate.value = false
    await reload()
  } catch (e) { error.value = message(e) }
}
</script>

<style scoped>
.ind-page{max-width:1100px;margin:auto;padding:24px}
.ind-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between}
.ind-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
table{width:100%;border-collapse:collapse;margin-top:16px}
th,td{border-bottom:1px solid #e2e8f0;padding:6px 8px;text-align:left;font-size:13px}
.mask{position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center}
form{background:#fff;padding:16px;display:grid;gap:10px;min-width:340px}
footer{display:flex;gap:10px;justify-content:flex-end}
</style>
