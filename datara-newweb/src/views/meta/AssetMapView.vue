<template>
  <main class="meta-page" aria-label="资产地图">
    <header class="meta-head">
      <div>
        <h1>资产地图</h1>
        <p>按库/域聚合资产分布（projects/{id}/assets）。</p>
      </div>
      <div class="meta-actions">
        <label>项目
          <select v-model="selectedProject" data-project-select @change="reload">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <label>关键字
          <input v-model.trim="keyword" placeholder="资产名/描述" @keyup.enter="reload">
        </label>
        <button type="button" :disabled="projectId === null" @click="reload">查询</button>
      </div>
    </header>

    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="loading" role="status">加载中…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="page.list.length === 0" data-empty>暂无资产</p>
    <template v-else>
      <section class="groups" data-asset-groups>
        <article v-for="g in groups" :key="g.key">
          <h2>{{ g.key }}</h2>
          <p class="count">{{ g.items.length }} 项</p>
          <ul>
            <li v-for="a in g.items" :key="a.id">
              <span class="name">{{ a.assetName }}</span>
              <span class="type">{{ a.assetType }}</span>
            </li>
          </ul>
        </article>
      </section>
      <table data-asset-table>
        <thead><tr><th>资产</th><th>类型</th><th>库</th><th>Schema</th><th>负责人</th><th>行数</th></tr></thead>
        <tbody>
          <tr v-for="a in page.list" :key="a.id">
            <td>{{ a.displayName || a.assetName }}</td>
            <td>{{ a.assetType }}</td>
            <td>{{ a.databaseName }}</td>
            <td>{{ a.schemaName || '—' }}</td>
            <td>{{ a.ownerName || '—' }}</td>
            <td>{{ a.rowCount ?? '—' }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type AssetPage } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const keyword = ref('')
const page = ref<AssetPage>({ total: 0, page: 1, pageSize: 50, list: [] })
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
const groups = computed(() => {
  const map = new Map<string, AssetPage['list']>()
  for (const a of page.value.list) {
    const key = a.databaseName || '未分库'
    const bucket = map.get(key)
    if (bucket) bucket.push(a)
    else map.set(key, [a])
  }
  return [...map.entries()].map(([key, items]) => ({ key, items }))
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
  if (projectId.value === null) { page.value = { total: 0, page: 1, pageSize: 50, list: [] }; return }
  loading.value = true
  error.value = ''
  try {
    page.value = await governanceApi.listAssets(projectId.value, { q: keyword.value || undefined })
  } catch (e) { error.value = message(e) } finally { loading.value = false }
}
</script>

<style scoped>
.meta-page{max-width:1100px;margin:auto;padding:24px}
.meta-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between}
.meta-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.groups{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:16px}
.groups article{border:1px solid #e2e8f0;border-radius:6px;padding:10px}
.groups ul{list-style:none;padding:0;display:grid;gap:4px}
.groups li{display:flex;justify-content:space-between;font-size:13px}
.count{color:#64748b;font-size:12px}
table{width:100%;border-collapse:collapse;margin-top:16px}
th,td{border-bottom:1px solid #e2e8f0;padding:6px 8px;text-align:left;font-size:13px}
</style>
