<template>
  <main class="pg" aria-label="血缘分析">
    <header class="pg-head">
      <h1 class="sec-head">血缘分析</h1>
      <p class="pg-desc">按资产查看上下游血缘图谱（assets/{id}/lineage）。</p>
    </header>

    <div class="toolbar">
      <label class="field"><span>项目</span>
        <select v-model="selectedProject" class="kw" data-project-select :disabled="assetLoading" @change="reloadAssets">
          <option value="">请选择项目</option>
          <option v-for="p in projects" :key="p.id" :value="String(p.id)">{{ p.name }}</option>
        </select>
      </label>
      <label class="field"><span>资产</span>
        <select v-model="selectedAsset" class="kw" data-asset-select :disabled="assetLoading || lineageLoading || assets.length === 0" @change="reloadLineage">
          <option value="">请选择资产</option>
          <option v-for="a in assets" :key="a.id" :value="String(a.id)">{{ a.databaseName }}.{{ a.assetName }}</option>
        </select>
      </label>

      <div class="seg" role="group" aria-label="血缘层级">
        <button type="button" :class="{ on: level === 'table' }" @click="level = 'table'">表级</button>
        <button type="button" :class="{ on: level === 'field' }" @click="level = 'field'">字段级</button>
      </div>

      <template v-if="assetId !== null">
        <span class="sep"></span>
        <div class="seg" role="group" aria-label="血缘方向">
          <button type="button" :class="{ on: direction === 'upstream' }" :disabled="lineageLoading" @click="setDirection('upstream')">上游</button>
          <button type="button" :class="{ on: direction === 'downstream' }" :disabled="lineageLoading" @click="setDirection('downstream')">下游</button>
          <button type="button" :class="{ on: direction === 'both' }" :disabled="lineageLoading" @click="setDirection('both')">双向</button>
        </div>
        <div class="seg" role="group" aria-label="血缘深度">
          <button v-for="d in DEPTHS" :key="d" type="button" :class="{ on: depth === d }" :disabled="lineageLoading" @click="setDepth(d)">{{ d }} 层</button>
        </div>
      </template>

      <span class="spacer"></span>
      <span v-if="projectId !== null && assets.length" class="hint">资产 {{ assets.length }} 个</span>
    </div>

    <div v-if="error" class="err-box" role="alert" data-error>
      <span>{{ error }}</span>
      <button type="button" class="op-btn retry" :disabled="loading" @click="retry">重试</button>
    </div>

    <div v-if="loading" class="panel" role="status" aria-live="polite">
      <div class="skeleton sk-row" style="width:40%"></div>
      <div class="skeleton sk-row" style="width:72%"></div>
      <div class="skeleton sk-row" style="width:56%"></div>
    </div>

    <div v-else-if="projectId === null" class="panel empty" data-no-project>
      <div class="e-title">请先选择项目</div>
      <div class="e-hint">在上方下拉框选择项目后，即可加载资产并查看血缘。</div>
    </div>

    <div v-else-if="assets.length === 0" class="panel empty" data-no-assets>
      <div class="e-title">暂无资产</div>
      <div class="e-hint">当前项目下没有资产，无法查看血缘图谱。</div>
    </div>

    <div v-else-if="assetId === null" class="panel empty" data-no-asset>
      <div class="e-title">请选择资产</div>
      <div class="e-hint">从资产下拉框中选择一个资产以加载血缘图谱。</div>
    </div>

    <template v-else>
      <div v-if="graph && graph.nodes.length === 0" class="panel empty" data-empty>
        <div class="e-title">暂无血缘关系</div>
        <div class="e-hint">该资产当前没有上下游节点。</div>
      </div>

      <template v-else-if="graph">
        <div class="legend" data-lineage-legend>
          <span class="lg-item"><i class="lg-dot lg-center"></i>中心资产（当前选中）</span>
          <span class="lg-item"><i class="lg-dot"></i>关联资产（上下游节点）</span>
          <span class="lg-item"><i class="lg-line"></i>血缘边（类型 / 过程引用）</span>
        </div>

        <section class="panel" data-lineage-graph>
          <div class="panel-hd">
            血缘图谱
            <span class="pill info">节点 {{ graph.nodes.length }} · 边 {{ graph.edges.length }}</span>
            <span class="spacer"></span>
            <span class="pill purple">{{ level === 'table' ? '表级' : '字段级' }}</span>
          </div>

          <template v-if="level === 'table'">
            <div class="sub-hd">节点（{{ graph.nodes.length }}）</div>
            <ul class="node-list" data-lineage-nodes>
              <li v-for="n in graph.nodes" :key="n.id" :class="{ cur: n.id === assetId }">
                <strong>
                  {{ n.displayName || n.assetName }}
                  <span v-if="n.id === assetId" class="pill info cur-tag">中心</span>
                </strong>
                <span>{{ n.databaseName }}{{ n.schemaName ? '.' + n.schemaName : '' }}</span>
              </li>
            </ul>

            <div class="sub-hd" style="margin-top:12px">边（{{ graph.edges.length }}）</div>
            <table class="tbl" data-lineage-edges>
              <thead><tr><th>来源</th><th>目标</th><th>类型</th><th>过程</th></tr></thead>
              <tbody>
                <tr v-for="e in graph.edges" :key="e.id">
                  <td>{{ nodeLabel(e.sourceAssetId) }}{{ e.sourceFieldName ? '.' + e.sourceFieldName : '' }}</td>
                  <td>{{ nodeLabel(e.targetAssetId) }}{{ e.targetFieldName ? '.' + e.targetFieldName : '' }}</td>
                  <td><span class="pill purple">{{ e.lineageType }}</span></td>
                  <td>{{ e.processRef || '—' }}</td>
                </tr>
                <tr v-if="!graph.edges.length"><td colspan="4" class="empty">暂无血缘边</td></tr>
              </tbody>
            </table>
          </template>

          <template v-else>
            <div v-if="!fieldEdges.length" class="empty" data-lineage-no-field>
              <div class="e-title">暂无字段级血缘</div>
              <div class="e-hint">当前图谱的边未携带字段映射（source_field_name / target_field_name 均为空）。</div>
            </div>
            <template v-else>
              <div class="sub-hd">字段映射（{{ fieldEdges.length }}）</div>
              <table class="tbl" data-lineage-fields>
                <thead><tr><th>来源字段</th><th>目标字段</th><th>类型</th><th>过程</th></tr></thead>
                <tbody>
                  <tr v-for="e in fieldEdges" :key="e.id">
                    <td class="mono">{{ fieldLabel(e.sourceAssetId, e.sourceFieldName) }}</td>
                    <td class="mono">{{ fieldLabel(e.targetAssetId, e.targetFieldName) }}</td>
                    <td><span class="pill purple">{{ e.lineageType }}</span></td>
                    <td>{{ e.processRef || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </template>
          </template>
        </section>
      </template>

      <div v-else class="panel empty" data-lineage-empty>
        <div class="e-title">尚未加载血缘</div>
        <div class="e-hint">血缘加载失败或尚未发起，请调整条件后重试。</div>
      </div>
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
/** 方向 / 深度下推 `GET assets/{id}/lineage`（后端 depth 约束 ge=1 le=10，故不提供「全链」）。 */
const direction = ref<'both' | 'upstream' | 'downstream'>('both')
const depth = ref(3)
/** 深度档位：对齐旧前端 1/2/3 层（后端上限 10，本页仅暴露前 3 档）。 */
const DEPTHS = [1, 2, 3] as const
/** 血缘层级：表级=节点/边；字段级=边携带的字段映射（sourceFieldName → targetFieldName）。 */
const level = ref<'table' | 'field'>('table')
const graph = ref<LineageGraph | null>(null)
/** 资产列表与血缘图谱各自独立 loading：避免并发请求互相提前结束 loading */
const assetLoading = ref(false)
const lineageLoading = ref(false)
const loading = computed(() => assetLoading.value || lineageLoading.value)
const error = ref('')
/** 错误框「重试」绑定操作：按错误来源设定，避免重试错配（资产失败→重载资产，血缘失败→重载血缘） */
const retry = ref<() => void>(() => reloadAssets)

let assetSeq = 0
let lineageSeq = 0

const routeProjectId = computed<number | null>(() => {
  const raw = route.params.projectId ?? route.query.projectId
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value !== undefined && value !== '' && Number.isInteger(n) && n > 0 ? n : null
})
const routeAssetId = computed<number | null>(() => {
  const raw = route.query.assetId
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

/** 节点索引：边表按 id 解析资产名（避免裸露 `#id`）。 */
const nodeById = computed(() => {
  const map = new Map<number, AssetRecord>()
  for (const n of graph.value?.nodes ?? []) map.set(n.id, n)
  return map
})

/** 资产显示名：优先 displayName → assetName → 退化 `#id`（不硬造名称）。 */
function nodeLabel(id: number): string {
  const n = nodeById.value.get(id)
  return n ? n.displayName || n.assetName || `#${id}` : `#${id}`
}

/** 字段级标签：`资产名.字段名`；字段名为空（常量/未采集）退化 '—'。 */
function fieldLabel(id: number, field: string): string {
  return field ? `${nodeLabel(id)}.${field}` : '—'
}

/** 字段级行：仅保留携带字段名的边（真实派生，不造数据）。 */
const fieldEdges = computed(() =>
  (graph.value?.edges ?? []).filter((e) => Boolean(e.sourceFieldName || e.targetFieldName)),
)

const message = (e: unknown): string => (e instanceof Error ? e.message : String(e))

async function init(): Promise<void> {
  try {
    const p = await listProjects()
    projects.value = p.list
    if (routeProjectId.value !== null) selectedProject.value = String(routeProjectId.value)
    if (selectedProject.value) await reloadAssets()
  } catch (e) {
    error.value = message(e)
    retry.value = init
  }
}
onMounted(init)

async function reloadAssets(): Promise<void> {
  const seq = ++assetSeq
  assetLoading.value = false
  lineageSeq += 1
  lineageLoading.value = false
  graph.value = null
  assets.value = []
  selectedAsset.value = ''
  error.value = ''
  if (projectId.value === null) return
  assetLoading.value = true
  error.value = ''
  try {
    const page = await governanceApi.listAssets(projectId.value)
    if (seq !== assetSeq) return
    assets.value = page.list
    const requested = routeAssetId.value
    if (requested !== null && page.list.some((asset) => asset.id === requested)) {
      selectedAsset.value = String(requested)
      await reloadLineage()
    }
  } catch (e) {
    if (seq === assetSeq) {
      error.value = message(e)
      retry.value = reloadAssets
    }
  } finally { if (seq === assetSeq) assetLoading.value = false }
}

async function reloadLineage(): Promise<void> {
  if (assetId.value === null) { graph.value = null; return }
  const seq = ++lineageSeq
  lineageLoading.value = true
  error.value = ''
  try {
    const data = await governanceApi.getLineage(assetId.value, { direction: direction.value, depth: depth.value })
    if (seq !== lineageSeq) return
    graph.value = data
  } catch (e) {
    if (seq === lineageSeq) {
      error.value = message(e)
      retry.value = reloadLineage
    }
  } finally { if (seq === lineageSeq) lineageLoading.value = false }
}

/** 分段控件切换（同值幂等跳过，避免重复请求）。 */
function setDirection(d: 'both' | 'upstream' | 'downstream'): void {
  if (direction.value === d) return
  direction.value = d
  void reloadLineage()
}

function setDepth(n: number): void {
  if (depth.value === n) return
  depth.value = n
  void reloadLineage()
}
</script>

<style scoped>
.sep{width:1px;height:18px;background:var(--border)}
.legend{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:0 2px}
.lg-item{display:inline-flex;align-items:center;gap:6px}
.lg-dot{display:inline-block;width:9px;height:9px;border-radius:3px;background:var(--border-strong)}
.lg-dot.lg-center{background:var(--primary)}
.lg-line{display:inline-block;width:22px;border-top:2px solid var(--primary)}
.node-list li.cur{border-color:rgba(22,104,220,.45);background:var(--primary-light)}
.cur-tag{margin-left:6px}
.toolbar .seg button:disabled{opacity:.45;cursor:not-allowed}
</style>
