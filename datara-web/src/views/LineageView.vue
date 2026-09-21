<script setup lang="ts">
/**
 * U6 血缘分析：全域表级/字段级血缘探查（只读）。
 * real 模式（I5 F26）：/lineage/tables + /lineage/fields 接真；mock 模式保留 dataStore 演示。
 * 表级：选中表 → 上游/下游 N 层切换 + 影响分析面板（通用推导）+ 中心表搜索。
 * 字段级：选中目标字段节点 → 转换细节弹层（F23：来源字段 + transform 表达式 + 语句/实例溯源）。
 * 三入口预置（F27）：路由 query ?table=（中心表）/ ?instance=&node=（实例追溯过滤）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { lineageProfile } from '../graph/profiles'
import GraphWorkbench from '../graph/workbench/GraphWorkbench.vue'
import { useGraphStore } from '../stores/graph'
import { dataStore } from '../services/mock/dataStore'
import { isMock } from '../services'
import { listFieldLineage, listTableLineage, type LineageEdgeRow } from '../services/lineageApi'
import type { FieldLineage, ImpactExample, MetaTable, TableLineage } from '../services/types'
import type { ImpactSubgraph } from '../graph/model'
import {
  buildFieldLineageDoc,
  buildTableLineageDoc,
  deriveImpact,
  filterByDepth,
  impactSummary,
} from '../services/mock/lineageUtils'

const graphStore = useGraphStore()
const route = useRoute()

const level = ref<'table' | 'field'>('table')
const direction = ref<'down' | 'up'>('down')
const depth = ref(1)
const selected = ref<string | null>(null)
const impactOpen = ref(true)
const fieldDetailOpen = ref(true)
const ready = ref(false)
const searchKw = ref('')

const tableLineage = ref<TableLineage[]>([])
const fieldLineage = ref<FieldLineage>({})
const impactExample = ref<ImpactExample | null>(null)
const metaTables = ref<MetaTable[]>([])
const edgeRows = ref<LineageEdgeRow[]>([])  // real 模式边明细（转换细节弹层溯源）

const baseDoc = computed(() =>
  level.value === 'table'
    ? buildTableLineageDoc(tableLineage.value, metaTables.value)
    : buildFieldLineageDoc(fieldLineage.value))

/** 表级选中后按 上游/下游 N 层 过滤；未就绪返回 null（GraphWorkbench 回退加载 seed） */
const doc = computed(() => {
  if (!ready.value) return null
  const base = baseDoc.value
  if (level.value === 'table' && selected.value) {
    return filterByDepth(base, selected.value, direction.value, depth.value)
  }
  return base
})

const impact = computed<ImpactSubgraph | null>(() => {
  if (level.value !== 'table' || !selected.value) return null
  return deriveImpact(selected.value, tableLineage.value, impactExample.value)
})

/* 字段级转换细节：选中目标字段节点 → 映射明细 + 语句溯源（同目标表的最近边行） */
const fieldDetail = computed(() => {
  if (level.value !== 'field' || !selected.value) return null
  const items = fieldLineage.value[selected.value]
  if (!items?.length) return null
  const tbl = selected.value.split('.')[0] ?? ''
  const stmtRow = edgeRows.value.find((r) => r.to === tbl) ?? null
  return { items, stmtRow }
})

/* 同步到 graphStore，使「血缘统计」浮窗读取当前构建文档 */
watch(doc, (d) => { if (d) graphStore.setDoc(d) })

watch(level, () => { selected.value = null; impactOpen.value = true; fieldDetailOpen.value = true })

function onSelect(id: string | null) {
  selected.value = id
  impactOpen.value = true
}

/** 中心表搜索：命中节点即选中；未命中提示（表级 N 层过滤与影响分析随之生效） */
function applySearch() {
  const kw = searchKw.value.trim()
  if (!kw) return
  const hit = baseDoc.value.nodes.find(
    (n) => n.id === kw || n.id.endsWith(`.${kw}`) || kw.endsWith(`.${n.id}`),
  )
  if (level.value !== 'table') level.value = 'table'
  if (hit) {
    selected.value = hit.id
    impactOpen.value = true
  } else {
    ElMessage.info(`血缘图中未找到表：${kw}`)
  }
}

async function reload() {
  const q = route.query
  if (isMock) {
    tableLineage.value = [...((await dataStore.list<TableLineage>('tableLineage')) ?? [])]
    fieldLineage.value = { ...((await dataStore.get<FieldLineage>('fieldLineage')) ?? {}) }
    impactExample.value = (await dataStore.get<ImpactExample>('impactExample')) ?? null
    metaTables.value = [...((await dataStore.list<MetaTable>('metaTables')) ?? [])]
  } else {
    try {
      const [edges, fields] = await Promise.all([
        listTableLineage(q.instance ? { instance_id: String(q.instance) } : {}),
        listFieldLineage(),
      ])
      let rows: LineageEdgeRow[] = edges
      if (q.node) rows = rows.filter((r) => r.nodeId === String(q.node))
      edgeRows.value = rows
      tableLineage.value = rows.map((r) => ({ from: r.from, to: r.to, task: r.task, wf: r.wf }))
      // 常量来源项（from=""）不构节点，视图层过滤
      const fl: FieldLineage = {}
      Object.entries(fields).forEach(([k, items]) => {
        const arr = items.filter((it) => it.from)
        if (arr.length) fl[k] = arr
      })
      fieldLineage.value = fl
      impactExample.value = null
      metaTables.value = []
    } catch (e) {
      ElMessage.error('血缘加载失败：' + (e instanceof Error ? e.message : String(e)))
    }
  }
  if (q.table) {
    searchKw.value = String(q.table)
    selected.value = String(q.table)
  }
  ready.value = true
}

onMounted(reload)
</script>

<template>
  <div class="lineage-page">
    <div class="lineage-toolbar">
      <div class="seg">
        <button :class="{ on: level === 'table' }" @click="level = 'table'">表级血缘</button>
        <button :class="{ on: level === 'field' }" @click="level = 'field'">字段级血缘</button>
      </div>
      <template v-if="level === 'table' && selected">
        <span class="sep" />
        <div class="seg">
          <button :class="{ on: direction === 'down' }" @click="direction = 'down'">下游</button>
          <button :class="{ on: direction === 'up' }" @click="direction = 'up'">上游</button>
        </div>
        <div class="seg">
          <button v-for="d in [1, 2, 3]" :key="d" :class="{ on: depth === d }" @click="depth = d">{{ d }}层</button>
        </div>
        <span class="hint">当前：{{ selected }}</span>
      </template>
      <span v-else-if="level === 'table'" class="hint">点击画布节点查看上/下游 N 层与影响分析</span>
      <span v-else class="hint">字段级血缘：点击目标字段节点查看加工转换细节</span>
      <span class="sep" />
      <input
        v-model="searchKw"
        class="search-in mono"
        placeholder="中心表搜索（回车定位）"
        @keyup.enter="applySearch"
      >
    </div>

    <GraphWorkbench
      :profile="lineageProfile"
      doc-id="lineage_global"
      :doc="doc"
      @select="onSelect"
    />

    <!-- 影响分析面板（表级 + 选中表） -->
    <div v-if="impact && impactOpen" class="impact-card">
      <div class="impact-head">
        <b>影响分析 · {{ impact.table }}</b>
        <button class="impact-close" @click="impactOpen = false">×</button>
      </div>
      <div class="impact-summary">{{ impactSummary(impact) }}</div>
      <div v-if="impact.downTables.length" class="impact-sec">
        <div class="sec-title">下游表</div>
        <div v-for="t in impact.downTables" :key="t.name" class="sec-row">
          <span>{{ t.name }}</span><i>{{ t.task }}</i>
        </div>
      </div>
      <div v-if="impact.downTasks.length" class="impact-sec">
        <div class="sec-title">下游任务</div>
        <div v-for="t in impact.downTasks" :key="t.name" class="sec-row">
          <span>{{ t.name }}</span><i>{{ t.wf }} · {{ t.type }}</i>
        </div>
      </div>
      <div v-if="impact.downIndicators.length" class="impact-sec">
        <div class="sec-title">受影响指标</div>
        <div v-for="m in impact.downIndicators" :key="m.code" class="sec-row">
          <span>{{ m.name }}</span><i>{{ m.code }}</i>
        </div>
      </div>
      <div v-if="impact.reports.length" class="impact-sec">
        <div class="sec-title">关联报表</div>
        <div v-for="r in impact.reports" :key="r" class="sec-row"><span>{{ r }}</span></div>
      </div>
      <div
        v-if="!impact.downTables.length && !impact.downTasks.length && !impact.downIndicators.length && !impact.reports.length"
        class="impact-empty"
      >暂无血缘（该表无下游影响对象）</div>
    </div>

    <!-- 字段级转换细节弹层（F23 展示核心：目标字段 ← 来源字段 + 加工表达式 + 语句/实例溯源） -->
    <div v-if="fieldDetail && fieldDetailOpen" class="impact-card">
      <div class="impact-head">
        <b>转换细节 · {{ selected }}</b>
        <button class="impact-close" @click="fieldDetailOpen = false">×</button>
      </div>
      <div class="impact-sec">
        <div class="sec-title">字段映射（{{ fieldDetail.items.length }}）</div>
        <div v-for="(it, i) in fieldDetail.items" :key="i" class="tr-row">
          <div class="tr-map mono"><b>{{ selected }}</b> ← {{ it.from }}</div>
          <div v-if="it.transform" class="tr-expr mono">{{ it.transform }}</div>
        </div>
      </div>
      <div v-if="fieldDetail.stmtRow" class="impact-sec tr-src">
        <div class="sec-title">采集溯源</div>
        <div class="tr-stmt mono">{{ fieldDetail.stmtRow.stmt }}</div>
        <div class="tr-meta">
          <span>实例 {{ fieldDetail.stmtRow.instanceId }}</span>
          <span>{{ fieldDetail.stmtRow.wf }} / {{ fieldDetail.stmtRow.task }}</span>
          <span v-if="fieldDetail.stmtRow.dsName">数据源 {{ fieldDetail.stmtRow.dsName }}</span>
        </div>
      </div>
      <div v-if="!fieldDetail.stmtRow" class="impact-empty">本字段无语句溯源信息（可能来自历史数据）</div>
    </div>
  </div>
</template>

<style scoped>
.lineage-page{position:relative;height:100%;display:flex;flex-direction:column}
.lineage-toolbar{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--border);background:#fff;z-index:5}
.seg{display:flex;gap:2px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:2px}
.seg button{border:none;background:transparent;padding:5px 14px;font-size:12px;cursor:pointer;color:var(--text-2);border-radius:var(--radius-sm);transition:all var(--dur-base) var(--ease);min-height:28px}
.seg button:hover{color:var(--text)}
.seg button.on{background:#fff;color:var(--primary);font-weight:600;box-shadow:0 1px 3px rgba(16,24,40,.14)}
.sep{width:1px;height:18px;background:var(--border)}
.hint{font-size:11.5px;color:var(--text-3)}
.impact-card{position:absolute;right:16px;bottom:16px;width:320px;max-height:60%;overflow:auto;background:#fff;border:1px solid var(--border-strong);border-radius:var(--radius-lg);box-shadow:0 8px 24px rgba(15,23,42,.12);z-index:20;font-size:12px}
.impact-head{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--border);background:var(--primary-light)}
.impact-head b{font-size:12.5px;color:var(--primary)}
.impact-close{border:none;background:none;font-size:16px;cursor:pointer;color:var(--text-3);line-height:1}
.impact-summary{padding:8px 12px;color:var(--text-2);border-bottom:1px dashed var(--border)}
.impact-sec{padding:8px 12px 2px}
.sec-title{font-size:11px;color:var(--text-3);margin-bottom:4px;font-weight:600}
.sec-row{display:flex;justify-content:space-between;gap:8px;padding:3px 0;border-bottom:1px solid var(--bg)}
.sec-row span{color:var(--text)}
.sec-row i{font-style:normal;font-size:10.5px;color:var(--text-3);white-space:nowrap}
.impact-empty{padding:16px 12px;text-align:center;color:var(--text-3)}
.search-in{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:4px 10px;font-size:12px;width:180px;outline:none;background:#fff;color:var(--text);transition:border-color var(--dur-base) var(--ease)}
.search-in:focus{border-color:var(--primary)}
.search-in::placeholder{color:var(--text-3)}
.tr-row{padding:4px 0;border-bottom:1px solid var(--bg)}
.tr-map{font-size:11.5px;color:var(--text-2)}
.tr-map b{color:var(--primary);font-weight:600}
.tr-expr{margin:2px 0 4px;padding:4px 8px;background:var(--bg);border-radius:var(--radius-sm);font-size:10.5px;color:var(--text-2);white-space:pre-wrap;word-break:break-all}
.tr-src{border-top:1px dashed var(--border)}
.tr-stmt{margin-bottom:6px;padding:6px 8px;background:var(--bg);border-radius:var(--radius-sm);font-size:10.5px;color:var(--text-2);white-space:pre-wrap;word-break:break-all;max-height:120px;overflow:auto}
.tr-meta{display:flex;flex-wrap:wrap;gap:10px;font-size:10.5px;color:var(--text-3)}
</style>