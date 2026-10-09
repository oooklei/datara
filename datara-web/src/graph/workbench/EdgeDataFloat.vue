<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { GEdge, GNode, GraphDocument } from '../model'
import { getInstanceDetail, isMock, listDefinitions, listInstancesPage } from '../../services'
import { capPreviewRows, EDGE_DATA_TYPE_VISUALS, type EdgeDataType } from './edgeData'

interface OutputDecl { name: string; type: string; desc?: string }

const props = defineProps<{
  doc: GraphDocument
  edge: GEdge
  upstream: GNode
  outputs: OutputDecl[]
  dataType: EdgeDataType
  previewLimit?: number
}>()

const loading = ref(false)
const loadError = ref('')
const columns = ref<string[]>([])
const rows = ref<unknown[][]>([])
const runId = ref('')
const hasRunRecord = ref(false)
const limit = computed(() => Math.min(Math.max(Math.floor(props.previewLimit ?? 100), 1), 100))

function previewOf(outputs: Record<string, unknown> | null | undefined): { columns: string[]; rows: unknown[][] } | null {
  const candidate = outputs?.result_preview ?? outputs?.sample ?? outputs?.preview
  if (!candidate || typeof candidate !== 'object') return null
  const value = candidate as { columns?: unknown; rows?: unknown }
  if (!Array.isArray(value.columns) || !Array.isArray(value.rows)) return null
  const cols = value.columns.map(String)
  const normalized = value.rows.map((row) => Array.isArray(row)
    ? row
    : cols.map((column) => (row as Record<string, unknown> | null)?.[column]))
  return { columns: cols, rows: normalized }
}

function fmt(value: unknown): string {
  if (value === null || value === undefined) return 'NULL'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

onMounted(async () => {
  if (isMock) return
  loading.value = true
  try {
    const defs = await listDefinitions({ pageSize: 200 })
    const code = defs.find((definition) => definition.id === props.doc.id)?.code
    if (!code) return
    const page = await listInstancesPage({ wfCode: String(code), pageSize: 1 })
    const latest = page.list[0]
    if (!latest) return
    const detail = await getInstanceDetail(latest.instanceId)
    const task = (detail.taskInstances ?? []).filter((item) => item.nodeId === props.upstream.id).slice(-1)[0]
    if (!task) return
    hasRunRecord.value = true
    runId.value = latest.instanceId
    const preview = previewOf(task.outputs)
    if (!preview) return
    columns.value = preview.columns
    rows.value = capPreviewRows(preview.rows, limit.value)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="edge-data-float">
    <div class="edge-summary">
      <span class="type-dot" :style="{ background: EDGE_DATA_TYPE_VISUALS[dataType].color }" />
      <strong>{{ upstream.data.name || upstream.id }}</strong>
      <span class="arrow">→</span>
      <code>{{ edge.target }}</code>
      <span class="type-pill">{{ dataType }}</span>
    </div>

    <section>
      <div class="section-title">输出 Schema</div>
      <div v-if="outputs.length" class="schema-list">
        <div v-for="output in outputs" :key="output.name" class="schema-row">
          <code>{{ output.name }}</code><span>{{ output.type }}</span><small>{{ output.desc || '—' }}</small>
        </div>
      </div>
      <div v-else class="empty">上游组件未声明输出 Schema；按 <code>{{ dataType }}</code> 类型连接。</div>
    </section>

    <section class="sample-section">
      <div class="section-title">最近运行样例 <small v-if="runId">{{ runId }} · 最多 {{ limit }} 行</small></div>
      <div v-if="loading" class="empty">正在读取最近运行记录…</div>
      <div v-else-if="loadError" class="empty error">样例读取失败：{{ loadError }}</div>
      <div v-else-if="!hasRunRecord" class="empty">暂无运行记录，仅展示 Schema / 类型。</div>
      <div v-else-if="!columns.length" class="empty">最近运行没有可预览的样例数据。</div>
      <div v-else class="sample-grid">
        <table class="tbl">
          <thead><tr><th>#</th><th v-for="column in columns" :key="column">{{ column }}</th></tr></thead>
          <tbody>
            <tr v-for="(row, rowIndex) in rows" :key="rowIndex">
              <td>{{ rowIndex + 1 }}</td><td v-for="(value, columnIndex) in row" :key="columnIndex"><code>{{ fmt(value) }}</code></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.edge-data-float{height:100%;display:flex;flex-direction:column;gap:12px;padding:12px;color:var(--text-2);font-size:12px}
.edge-summary{display:flex;align-items:center;gap:8px;padding-bottom:10px;border-bottom:1px solid var(--border)}
.type-dot{width:9px;height:9px;border-radius:50%}.arrow{color:var(--text-3)}
.type-pill{margin-left:auto;padding:2px 7px;border:1px solid var(--border);border-radius:999px;font:10px var(--mono,monospace);text-transform:uppercase}
.section-title{font-weight:700;color:var(--text-1);margin-bottom:6px}.section-title small{margin-left:8px;font-weight:400;color:var(--text-3)}
.schema-list{border:1px solid var(--border);border-radius:4px}.schema-row{display:grid;grid-template-columns:120px 80px 1fr;gap:8px;padding:6px 8px;border-top:1px solid var(--border)}.schema-row:first-child{border-top:0}.schema-row span{color:var(--primary)}.schema-row small{color:var(--text-3)}
.sample-section{min-height:0;display:flex;flex:1;flex-direction:column}.sample-grid{min-height:0;overflow:auto;border:1px solid var(--border);border-radius:4px}.empty{padding:18px;text-align:center;color:var(--text-3);border:1px dashed var(--border);border-radius:4px}.empty.error{color:var(--danger)}
.sample-grid th,.sample-grid td{white-space:nowrap}.sample-grid th:first-child,.sample-grid td:first-child{width:34px;text-align:right;color:var(--text-3)}
</style>

