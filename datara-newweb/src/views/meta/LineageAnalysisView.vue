<template>
  <main class="meta-page" aria-label="血缘分析">
    <header class="meta-head">
      <div>
        <h1>血缘分析</h1>
        <p>按资产查看上下游血缘图谱（assets/{id}/lineage）。</p>
      </div>
      <div class="meta-actions">
        <label>项目
          <select v-model="selectedProject" data-project-select @change="reloadAssets">
            <option value="">请选择项目</option>
            <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
          </select>
        </label>
        <label>资产
          <select v-model="selectedAsset" data-asset-select :disabled="assets.length === 0" @change="reloadLineage">
            <option value="">请选择资产</option>
            <option v-for="a in assets" :key="a.id" :value="String(a.id)">
              {{ a.databaseName }}.{{ a.assetName }}
            </option>
          </select>
        </label>
        <label>方向
          <select v-model="direction" @change="reloadLineage">
            <option value="both">both</option>
            <option value="upstream">upstream</option>
            <option value="downstream">downstream</option>
          </select>
        </label>
      </div>
    </header>

    <p v-if="error" role="alert" data-error>{{ error }}</p>
    <p v-if="loading" role="status">加载中…</p>
    <p v-else-if="projectId === null" data-no-project>请先选择项目</p>
    <p v-else-if="selectedAsset === ''" data-no-asset>请选择资产</p>
    <template v-else>
      <p v-if="graph && graph.nodes.length === 0" data-empty>暂无血缘关系</p>
      <section v-else-if="graph" data-lineage-graph>
        <h2>节点（{{ graph.nodes.length }}）</h2>
        <ul class="nodes">
          <li v-for="n in graph.nodes" :key="n.id">
            <strong>{{ n.displayName || n.assetName }}</strong>
            <span>{{ n.databaseName }}{{ n.schemaName ? '.' + n.schemaName : '' }}</span>
          </li>
        </ul>
        <h2>边（{{ graph.edges.length }}）</h2>
        <table>
          <thead><tr><th>来源资产</th><th>目标资产</th><th>类型</th><th>过程</th></tr></thead>
          <tbody>
            <tr v-for="e in graph.edges" :key="e.id">
              <td>#{{ e.sourceAssetId }}{{ e.sourceFieldName ? ':' + e.sourceFieldName : '' }}</td>
              <td>#{{ e.targetAssetId }}{{ e.targetFieldName ? ':' + e.targetFieldName : '' }}</td>
              <td>{{ e.lineageType }}</td>
              <td>{{ e.processRef || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { governanceApi, type AssetRecord, type LineageGraph } from '../../services/rebuild/governanceApi'
import { listProjects, type ProjectSummary } from '../../services/rebuild/projectApi'

const route = useRoute()
const projects = ref<ProjectSummary[]>([])
const selectedProject = ref('')
const assets = ref<AssetRecord[]>([])
const selectedAsset = ref('')
const direction = ref<'both' | 'upstream' | 'downstream'>('both')
const graph = ref<LineageGraph | null>(null)
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
const assetId = computed<number | null>(() => {
  const n = Number(selectedAsset.value)
  return selectedAsset.value !== '' && Number.isInteger(n) && n > 0 ? n : null
})

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

onMounted(async () => {
  try {
    const p = await listProjects()
    projects.value = p.list
    if (routeProjectId.value !== null) selectedProject.value = String(routeProjectId.value)
    if (selectedProject.value) await reloadAssets()
  } catch (e) { error.value = message(e) }
})

async function reloadAssets(): Promise<void> {
  graph.value = null
  selectedAsset.value = ''
  if (projectId.value === null) { assets.value = []; return }
  loading.value = true
  error.value = ''
  try {
    const page = await governanceApi.listAssets(projectId.value)
    assets.value = page.list
  } catch (e) { error.value = message(e) } finally { loading.value = false }
}

async function reloadLineage(): Promise<void> {
  if (assetId.value === null) { graph.value = null; return }
  loading.value = true
  error.value = ''
  try {
    graph.value = await governanceApi.getLineage(assetId.value, { direction: direction.value, depth: 3 })
  } catch (e) { error.value = message(e) } finally { loading.value = false }
}
</script>

<style scoped>
.meta-page{max-width:1100px;margin:auto;padding:24px}
.meta-head{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between}
.meta-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.nodes{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px;list-style:none;padding:0}
.nodes li{border:1px solid #e2e8f0;border-radius:6px;padding:8px;display:grid;gap:4px}
.nodes span{color:#64748b;font-size:12px}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{border-bottom:1px solid #e2e8f0;padding:6px 8px;text-align:left;font-size:13px}
</style>
