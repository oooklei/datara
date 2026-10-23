<template>
  <main class="meta-page" aria-label="元数据目录">
    <header class="meta-head">
      <div>
        <h1>元数据目录</h1>
        <p>资产与字段清单（assets/{id} 明细）。</p>
      </div>
      <div class="meta-actions">
        <label>项目
          <select v-model="selectedProject" data-project-select @change="reload">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <label>类型
          <input v-model.trim="assetType" placeholder="table/view" @keyup.enter="reload">
        </label>
        <button type="button" :disabled="projectId === null" @click="reload">查询</button>
      </div>
    </header>

    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="loading" role="status">加载中…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="page.list.length === 0" data-empty>暂无资产</p>

    <div v-else class="split">
      <ul class="catalog" data-catalog-list>
        <li v-for="a in page.list" :key="a.id">
          <button type="button" :class="{ active: selectedId === a.id }" @click="select(a.id)">
            {{ a.assetName }}
            <small>{{ a.assetType }} · {{ a.databaseName }}</small>
          </button>
        </li>
      </ul>
      <section class="detail" data-catalog-detail>
        <p v-if="!detail">选择左侧资产查看字段</p>
        <template v-else>
          <h2>{{ detail.displayName || detail.assetName }}</h2>
          <p class="meta">{{ detail.sourceSystem }} / {{ detail.databaseName }}{{ detail.schemaName ? '.' + detail.schemaName : '' }}</p>
          <p>{{ detail.description || '无描述' }}</p>
          <table>
            <thead><tr><th>#</th><th>字段</th><th>类型</th><th>可空</th><th>描述</th></tr></thead>
            <tbody>
              <tr v-for="f in detail.fields ?? []" :key="f.id">
                <td>{{ f.ordinalPosition }}</td>
                <td>{{ f.fieldName }}</td>
                <td>{{ f.dataType }}</td>
                <td>{{ f.nullable ? '是' : '否' }}</td>
                <td>{{ f.description || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type AssetPage, type AssetRecord } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const assetType = ref('')
const page = ref<AssetPage>({ total: 0, page: 1, pageSize: 50, list: [] })
const detail = ref<AssetRecord | null>(null)
const selectedId = ref<number | null>(null)
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
  detail.value = null
  selectedId.value = null
  if (projectId.value === null) { page.value = { total: 0, page: 1, pageSize: 50, list: [] }; return }
  loading.value = true
  error.value = ''
  try {
    page.value = await governanceApi.listAssets(projectId.value, { assetType: assetType.value || undefined })
  } catch (e) { error.value = message(e) } finally { loading.value = false }
}

async function select(id: number): Promise<void> {
  selectedId.value = id
  error.value = ''
  try {
    detail.value = await governanceApi.getAsset(id)
  } catch (e) { error.value = message(e) }
}
</script>

<style scoped>
.meta-page{max-width:1200px;margin:auto;padding:24px}
.meta-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between}
.meta-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.split{display:grid;grid-template-columns:260px 1fr;gap:16px;margin-top:16px}
.catalog{list-style:none;padding:0;display:grid;gap:4px;align-content:start}
.catalog button{width:100%;text-align:left;border:1px solid #e2e8f0;background:#fff;border-radius:6px;padding:8px;cursor:pointer;display:grid}
.catalog button.active{border-color:#2563eb;background:#eff6ff}
.catalog small{color:#64748b}
.detail{border:1px solid #e2e8f0;border-radius:6px;padding:12px}
.meta{color:#64748b;font-size:12px}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{border-bottom:1px solid #e2e8f0;padding:6px 8px;text-align:left;font-size:13px}
</style>
