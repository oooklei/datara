<script setup lang="ts">
/**
 * 任务中心（/dag）—— 统一任务流入口，替代原「批处理与同步 / 流数据处理 / DAG工作流」三处分立导航。
 * 统一布局（不搞两套）：四个任务视角（工作流/同步/ETL/流）均为「画布直达 + 看列表弹窗」同一模式——
 * 打开即默认显示该类型上次编辑的任务画布（per-type localStorage datara.dag.last[.type]），
 * 点「看列表」弹窗显示该类型任务列表，行内「可视化编排」原位切换内嵌画布（不跳路由）。
 * 画布组件按类型分发：工作流/同步 → DAG 编排（组件库互通）；ETL → ETL设计器；流 → 流设计器。
 * 运行监控视角为运行实例列表；同步监控走同步任务列表/详情（I6 syncApi 接真）；告警与SLA独立视角。
 * 同步列表为监控视角（批次记录）；独立同步向导已移除（意见⑬：同步编排模板归 I6 C23）。
 * F56d：候选池双态 —— real 从后端 workflow-definitions 拉全量按 tags（同步/ETL/流）过滤，
 * mock 保留 seed 文档池；运行监控切 InstanceRunsView（纯 mock 演示页 DagRunsView 删除）。
 */
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { graphService, isMock, listDefinitions, SYNC_TAG, ETL_TAG, STREAM_TAG } from '../services'
import { listSeedTaskDocs } from '../services/mock/seed'
import DagDesignView from './DagDesignView.vue'
import DagListView from './DagListView.vue'
import EtlDesignView from './EtlDesignView.vue'
import EtlListView from './etl/EtlListView.vue'
import StreamDesignView from './StreamDesignView.vue'
import StreamListView from './stream/StreamListView.vue'
import SyncListView from './sync/SyncListView.vue'
import InstanceRunsView from './dag/InstanceRunsView.vue'
import DagAlarmView from './dag/DagAlarmView.vue'

const route = useRoute()
const router = useRouter()

type TabKey = 'wf' | 'sync' | 'etl' | 'stream' | 'runs' | 'alarm'
const tabs: { k: TabKey; label: string; icon: string; kind: 'task' | 'runs' | 'alarm' }[] = [
  { k: 'wf', label: '工作流', icon: '⑃', kind: 'task' },
  { k: 'sync', label: '同步任务', icon: '⇄', kind: 'task' },
  { k: 'etl', label: 'ETL任务', icon: '⚙', kind: 'task' },
  { k: 'stream', label: '流任务', icon: '≈', kind: 'task' },
  { k: 'runs', label: '运行监控', icon: '▶', kind: 'runs' },
  { k: 'alarm', label: '告警与SLA', icon: '🖂', kind: 'alarm' },
]
const qtab = String(route.query.tab ?? '')
const tab = ref<TabKey>(tabs.some((t) => t.k === qtab) ? (qtab as TabKey) : 'wf')

function switchTab(k: TabKey) {
  tab.value = k
  router.replace({ query: { ...route.query, tab: k } }).catch(() => {})
}

/* ---- 各任务视角的默认画布文档（打开即达可视化核心） ---- */
const docIds = ref<Record<string, string>>({ wf: '', sync: '', etl: '', stream: '' })
const listOpen = ref(false)

function lsGet(key: string): string {
  try { return localStorage.getItem(key) ?? '' } catch { return '' }
}
function lsSet(key: string, v: string) {
  try { localStorage.setItem(key, v) } catch { /* 忽略隐私模式 */ }
}

/** real 候选池：后端定义全量（一次拉取，定义量几十级）；tags 供 poolOf 过滤 */
const defPool = ref<{ id: string; name: string; tags: string[] }[]>([])

async function loadDefPool() {
  try {
    const defs = await listDefinitions({ pageNo: 1, pageSize: 500 })
    defPool.value = defs.map((d) => ({ id: d.id, name: d.name, tags: d.tags ?? [] }))
  } catch { /* 后端未就绪时留空（画布区显示空态） */ }
}

/** 某任务类型的候选图文档池（F56d 双态）：mock = seed 文档池；
 * real = 按定义 tags 过滤 —— wf = 不含「同步」/「ETL」/「流」，sync/etl/stream = 含对应标签 */
function poolOf(t: 'wf' | 'sync' | 'etl' | 'stream'): { id: string; name: string; type?: string }[] {
  if (isMock) {
    return listSeedTaskDocs().filter((d) => (t === 'wf' ? (!d.type || d.type === 'batch') : d.type === t))
  }
  const has = (d: { tags: string[] }, tag: string) => d.tags.includes(tag)
  return defPool.value
    .filter((d) => {
      if (t === 'sync') return has(d, SYNC_TAG)
      if (t === 'etl') return has(d, ETL_TAG)
      if (t === 'stream') return has(d, STREAM_TAG)
      return !has(d, SYNC_TAG) && !has(d, ETL_TAG) && !has(d, STREAM_TAG)
    })
    .map((d) => ({ id: d.id, name: d.name }))
}

onMounted(async () => {
  if (isMock) {
    /* mock：工作流全局 last（校验可加载，兼容用户自建持久化工作流）→ 第一个 batch 文档 */
    const lastWf = lsGet('datara.dag.last')
    if (lastWf) {
      const d = await graphService.get(lastWf)
      if (d) docIds.value.wf = lastWf
    }
    if (!docIds.value.wf) docIds.value.wf = poolOf('wf')[0]?.id ?? 'wf_order_daily'
  } else {
    /* real（F56d）：一次拉全量构建候选池；wf last 优先，否则取后端定义列表第一个 */
    await loadDefPool()
    const lastWf = lsGet('datara.dag.last')
    if (lastWf) docIds.value.wf = lastWf
    if (!docIds.value.wf) docIds.value.wf = defPool.value[0]?.id ?? ''
  }
  /* 同步/ETL/流（F56d 双态）：per-type last（须在候选池内）→ 候选池第一个，无 dataStore 兜底 */
  for (const t of ['sync', 'etl', 'stream'] as const) {
    const last = lsGet(`datara.dag.last.${t}`)
    const pool = poolOf(t)
    docIds.value[t] = (last && pool.some((d) => d.id === last)) ? last : (pool[0]?.id ?? '')
  }
})

/* 「看列表」弹窗内选中任务 → 切换内嵌画布（不跳路由，弹窗即关） */
function onOpenDoc(t: TabKey, id: string) {
  if (!id) return
  docIds.value = { ...docIds.value, [t]: id }
  listOpen.value = false
  lsSet(t === 'wf' ? 'datara.dag.last' : `datara.dag.last.${t}`, id)
}

const listTitles: Record<string, string> = {
  wf: '工作流列表', sync: '同步任务（监控视角）', etl: 'ETL任务列表', stream: '流任务列表',
}
</script>

<template>
  <div class="tc">
    <!-- 顶部视角页签栏 -->
    <div class="tc-tabs">
      <button
        v-for="t in tabs" :key="t.k"
        class="tc-tab" :class="{ on: tab === t.k }"
        @click="switchTab(t.k)"
      ><span class="tc-ic">{{ t.icon }}</span>{{ t.label }}</button>
      <span class="spacer" />
      <button v-if="tabs.find((t) => t.k === tab)?.kind === 'task'" class="op-btn" @click="listOpen = true">看列表</button>
    </div>

    <!-- 视角内容区：四个任务视角统一「画布直达」 -->
    <div class="tc-body">
      <div v-if="tab === 'wf' && docIds.wf" class="tc-canvas">
        <DagDesignView :key="`wf-${docIds.wf}`" :doc-id="docIds.wf" />
      </div>
      <div v-else-if="tab === 'sync' && docIds.sync" class="tc-canvas">
        <DagDesignView :key="`sync-${docIds.sync}`" :doc-id="docIds.sync" />
      </div>
      <div v-else-if="tab === 'etl' && docIds.etl" class="tc-canvas">
        <EtlDesignView :key="`etl-${docIds.etl}`" :doc-id="docIds.etl" />
      </div>
      <div v-else-if="tab === 'stream' && docIds.stream" class="tc-canvas">
        <StreamDesignView :key="`stream-${docIds.stream}`" :doc-id="docIds.stream" />
      </div>

      <template v-else-if="tab === 'runs'">
        <!-- F56d：运行实例接引擎真数据（InstanceRunsView），纯 mock 演示页 DagRunsView 已删除 -->
        <InstanceRunsView />
      </template>

      <div v-else-if="tab === 'alarm'" class="tc-alarm-wrap">
        <!-- F56e：告警与SLA 为演示模块，页签内容顶部主动提示（与顶栏「演示数据」标识同规则） -->
        <div class="tc-demo-tip">演示数据 · 告警与SLA 为本期范围外模块，页面数据为演示样例</div>
        <DagAlarmView />
      </div>
    </div>

    <!-- 看列表弹窗（可视化直达原则：列表按需弹出；行内「可视化编排」原位切换画布） -->
    <el-dialog v-model="listOpen" :title="listTitles[tab]" width="1000px" :append-to-body="true">
      <DagListView v-if="tab === 'wf'" embed @open="onOpenDoc('wf', $event)" />
      <SyncListView v-else-if="tab === 'sync'" />
      <EtlListView v-else-if="tab === 'etl'" embed @open="onOpenDoc('etl', $event)" />
      <StreamListView v-else-if="tab === 'stream'" embed @open="onOpenDoc('stream', $event)" />
      <!-- 底部明确出口：弹窗覆盖画布后，一键返回 DAG 窗口 -->
      <template #footer>
        <div class="dlg-foot-bar">
          <span class="dlg-hint">行内「可视化编排」可原位切换画布；关闭即返回当前任务画布</span>
          <button class="tb-new" @click="listOpen = false">✕ 返回画布</button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.tc{display:flex;flex-direction:column;height:100%}
.tc-tabs{display:flex;align-items:center;gap:2px;padding:0 14px;background:#fff;border-bottom:1px solid var(--border);flex-shrink:0}
.tc-tab{border:none;background:none;padding:11px 16px;font-size:13px;color:var(--text-2);cursor:pointer;border-bottom:2px solid transparent;display:flex;align-items:center;gap:6px;transition:color var(--dur-base) var(--ease),border-color var(--dur-base) var(--ease)}
.tc-tab:hover{color:var(--primary)}
.tc-tab.on{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}
.tc-ic{font-size:12px;opacity:.75}
.tc-tab.on .tc-ic{opacity:1}
.spacer{flex:1}
.op-btn{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--primary);background:var(--primary-light);border-radius:var(--radius-sm);padding:4px 14px;font-size:12px;font-weight:600;cursor:pointer;color:var(--primary);margin-bottom:7px;transition:all var(--dur-base) var(--ease)}
.op-btn:hover{background:var(--primary);color:#fff;box-shadow:var(--shadow-primary)}
.tc-body{flex:1;min-height:0;display:flex;flex-direction:column;overflow:auto}
.tc-canvas{flex:1;min-height:0;display:flex;flex-direction:column}
/* F56e：演示页签顶部提示条（低饱和描边，不做警告色） */
.tc-alarm-wrap{display:flex;flex-direction:column;min-height:0}
.tc-demo-tip{margin:10px 14px 0;padding:6px 12px;border:1px solid var(--border);border-radius:var(--radius-lg);font-size:12px;color:var(--text-3);background:var(--bg)}
/* 看列表弹窗底部出口：提示文案 + 返回画布主按钮 */
.dlg-foot-bar{display:flex;align-items:center;justify-content:space-between;gap:12px}
.dlg-hint{color:var(--text-3);font-size:12px}
.dlg-foot-bar .tb-new{padding:7px 18px}
</style>
