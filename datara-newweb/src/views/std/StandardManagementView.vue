<template>
  <main class="std-page" aria-label="标准管理">
    <header class="std-head">
      <div>
        <h1>标准管理</h1>
        <p>数据标准定义与结构校验（standards / standards/check）。</p>
      </div>
      <div class="std-actions">
        <label>项目
          <select v-model="selectedProject" data-project-select @change="reload">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <button type="button" :disabled="projectId === null" @click="openCreate">新建标准</button>
      </div>
    </header>

    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="loading" role="status">加载中…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="page.list.length === 0" data-empty>暂无标准</p>

    <table v-else data-std-list>
      <thead><tr><th>编码</th><th>名称</th><th>数据类型</th><th>表达式</th><th>状态</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="s in page.list" :key="s.id">
          <td>{{ s.code }}</td>
          <td>{{ s.name }}</td>
          <td>{{ s.dataType }}</td>
          <td>{{ s.expression || '—' }}</td>
          <td>{{ s.status }}</td>
          <td><button type="button" @click="check(s)">校验</button></td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="mask" @click.self="showCreate = false">
      <form role="dialog" aria-label="新建标准" @submit.prevent="save">
        <h2>新建标准</h2>
        <label>编码<input v-model.trim="form.code" required></label>
        <label>名称<input v-model.trim="form.name" required></label>
        <label>数据类型<input v-model.trim="form.dataType" required placeholder="string/int/decimal"></label>
        <label>表达式<input v-model.trim="form.expression" placeholder="如 not_null / length<=64"></label>
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

    <pre v-if="checkResult" data-check-result>{{ checkResult }}</pre>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  governanceApi,
  type DefinitionStatus,
  type StandardDefinition,
  type StandardPage,
} from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const page = ref<StandardPage>({ total: 0, list: [] })
const loading = ref(false)
const error = ref('')
const showCreate = ref(false)
const checkResult = ref('')
const form = reactive({
  code: '',
  name: '',
  dataType: '',
  expression: '',
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
  checkResult.value = ''
  if (projectId.value === null) { page.value = { total: 0, list: [] }; return }
  loading.value = true
  error.value = ''
  try {
    page.value = await governanceApi.listStandards(projectId.value)
  } catch (e) { error.value = message(e) } finally { loading.value = false }
}

function openCreate(): void {
  Object.assign(form, { code: '', name: '', dataType: '', expression: '', description: '', status: 'draft' })
  showCreate.value = true
}

async function save(): Promise<void> {
  if (projectId.value === null) return
  error.value = ''
  try {
    await governanceApi.createStandard(projectId.value, { ...form })
    showCreate.value = false
    await reload()
  } catch (e) { error.value = message(e) }
}

async function check(s: StandardDefinition): Promise<void> {
  if (projectId.value === null) return
  error.value = ''
  try {
    const res = await governanceApi.checkStandard(projectId.value, { standardId: s.id })
    checkResult.value = JSON.stringify(res, null, 2)
  } catch (e) { error.value = message(e) }
}
</script>

<style scoped>
.std-page{max-width:1100px;margin:auto;padding:24px}
.std-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between}
.std-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
table{width:100%;border-collapse:collapse;margin-top:16px}
th,td{border-bottom:1px solid #e2e8f0;padding:6px 8px;text-align:left;font-size:13px}
.mask{position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center}
form{background:#fff;padding:16px;display:grid;gap:10px;min-width:320px}
footer{display:flex;gap:10px;justify-content:flex-end}
pre{background:#0f172a;color:#e2e8f0;padding:12px;overflow:auto;margin-top:16px}
</style>
