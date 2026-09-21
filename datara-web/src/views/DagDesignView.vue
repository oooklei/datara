<script setup lang="ts">
/**
 * DAG 工作台（统一编排窗口）—— 五页签：设计 / 依赖 / 运行 / 日志 / 变量。
 * - 设计：GraphWorkbench 画布（dag profile，任务节点双击语义见节点说明）；
 * - 依赖：节点间依赖边配置 —— 部分结果数据依赖三级粒度（结果表→字段子集→行过滤表达式）
 *         + 同周期/同批次依赖条件（写回 GEdge.partial，随版本保存）；
 * - 运行：本工作流的运行实例（wfInstances）与节点状态；
 * - 日志：运行日志面板（run store）；
 * - 变量：工作流变量管理（WfVarPanel，管理与使用分离，Inspector 仅引用）。
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { dagProfile } from '../graph/profiles'
import GraphWorkbench from '../graph/workbench/GraphWorkbench.vue'
import LogPanel from '../graph/workbench/panels/LogPanel.vue'
import WfVarPanel from '../graph/workbench/panels/WfVarPanel.vue'
import { useGraphStore } from '../stores/graph'
import { useAuthStore } from '../stores/auth'
import { isMock } from '../services'
import { dataStore, ST } from '../services/mock/dataStore'
import type { GEdge } from '../graph/model'
import type { MetaTable, WfInstance } from '../services/types'

/**
 * 两种用法：
 * 1. 独立路由 /dag/design/:id（route.params.id）；
 * 2. 任务中心「工作流」视角内嵌（props.docId 覆盖，docId 变化通过 :key 强刷重挂载）。
 * 每次打开编排即记录「上次编辑的工作流」（datara.dag.last），任务中心默认打开它。
 */
const props = defineProps<{ docId?: string }>()
const route = useRoute()
const routeId = String(route.params.id ?? '')
const docId = computed(() => props.docId ?? routeId)
const graphStore = useGraphStore()
const auth = useAuthStore()

type TabKey = 'design' | 'depend' | 'runs' | 'logs' | 'vars'
const tab = ref<TabKey>('design')
const tabs: { k: TabKey; label: string; icon: string }[] = [
  { k: 'design', label: '设计', icon: '✎' },
  { k: 'depend', label: '依赖', icon: '⧉' },
  { k: 'runs', label: '运行', icon: '▶' },
  { k: 'logs', label: '日志', icon: '▤' },
  { k: 'vars', label: '变量', icon: '$' },
]

const doc = computed(() => graphStore.doc)
const metaTables = ref<MetaTable[]>([])
const instances = ref<WfInstance[]>([])

onMounted(async () => {
  // 记录「上次编辑的工作流」：任务中心默认直接打开它（可视化直达原则）
  try { localStorage.setItem('datara.dag.last', docId.value) } catch { /* 忽略隐私模式 */ }
  /* F56d：metaTables（依赖页表选项）/ wfInstances（运行页演示实例）为 mock 数据源，
     real 不再读取 dataStore —— real 运行实例统一见 /dag/instances（InstanceRunsView） */
  if (!isMock) return
  const [t, ins] = await Promise.all([
    dataStore.list<MetaTable>('metaTables'),
    dataStore.list<WfInstance>('wfInstances'),
  ])
  metaTables.value = [...(t ?? [])]
  /* 运行实例按工作流名匹配（图文档 id 与 wfInstances 的 WF 编号是两套演示数据，以名称对齐） */
  const name = doc.value?.name ?? ''
  instances.value = (ins ?? []).filter((i) => i.wfName === name || i.wf === docId.value)
})

function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
function nStatusCls(s: string): string {
  return s === 'success' ? 'ok' : s === 'failed' ? 'err' : s === 'running' ? 'info' : 'off'
}

/* ================= 依赖页：部分结果数据依赖（三级粒度） ================= */
const nodeName = (id: string) => doc.value?.nodes.find((n) => n.id === id)?.data.name ?? id

const depEdges = computed<GEdge[]>(() => (doc.value ? [...doc.value.edges] : []))

const tableOptions = computed(() => metaTables.value.map((t) => t.name))

function scopeLabel(s: EdgeScope): string {
  return s === 'cycle' ? '同周期' : s === 'batch' ? '同批次' : '同周期+同批次'
}
type EdgeScope = NonNullable<GEdge['partial']>['scope']

function togglePartial(e: GEdge, ev: Event) {
  if (!auth.canEdit || !doc.value) return
  const on = (ev.target as HTMLInputElement).checked
  if (on) {
    e.partial = { table: tableOptions.value[0] ?? '', fields: [], filter: '', scope: 'cycle' }
  } else {
    delete e.partial
  }
  graphStore.markDirty()
}

function setFields(e: GEdge, raw: string) {
  if (!e.partial || !auth.canEdit) return
  e.partial.fields = raw.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
  graphStore.markDirty()
}

function fieldsText(e: GEdge): string {
  return e.partial?.fields.join(',') ?? ''
}

function onScope(e: GEdge, ev: Event) {
  if (!e.partial || !auth.canEdit) return
  e.partial.scope = (ev.target as HTMLSelectElement).value as EdgeScope
  graphStore.markDirty()
}

function onTable(e: GEdge, ev: Event) {
  if (!e.partial || !auth.canEdit) return
  e.partial.table = (ev.target as HTMLSelectElement).value
  graphStore.markDirty()
}

function onFilter(e: GEdge, ev: Event) {
  if (!e.partial || !auth.canEdit) return
  e.partial.filter = (ev.target as HTMLInputElement).value
  graphStore.markDirty()
}

function partialDesc(e: GEdge): string {
  if (!e.partial) return '全量依赖'
  const f = e.partial.fields.length ? `${e.partial.fields.length} 字段` : '全字段'
  const r = e.partial.filter ? ' · 行过滤' : ''
  return `部分依赖 · ${e.partial.table} · ${f}${r} · ${scopeLabel(e.partial.scope)}`
}
</script>

<template>
  <div class="wbt">
    <!-- 页签栏 -->
    <div class="wbt-tabs">
      <button
        v-for="t in tabs" :key="t.k"
        class="wbt-tab" :class="{ on: tab === t.k }"
        @click="tab = t.k"
      ><span class="wbt-ic">{{ t.icon }}</span>{{ t.label }}</button>
    </div>

    <!-- 设计：画布（保持挂载，切换页签不丢状态） -->
    <div v-show="tab === 'design'" class="wbt-design">
      <GraphWorkbench :key="docId" :profile="dagProfile" :doc-id="docId" />
    </div>

    <!-- 依赖：部分结果数据依赖配置 -->
    <div v-if="tab === 'depend'" class="wbt-page">
      <div class="card panel">
        <div class="dep-head">
          <div>
            <div class="dep-title">任务依赖 · 部分结果数据</div>
            <div class="dep-desc">依赖边可配置仅依赖上一节点输出的部分结果数据（结果表 → 字段子集 → 行过滤表达式三级粒度），并设置同周期/同批次依赖条件；缺省为全量依赖。</div>
          </div>
          <span v-if="!auth.canEdit" class="pill off">只读（analyst/viewer）</span>
        </div>
        <table v-if="depEdges.length" class="tbl">
          <thead>
            <tr><th style="width:210px">依赖边</th><th style="width:110px">依赖模式</th><th>部分依赖配置</th></tr>
          </thead>
          <tbody>
            <tr v-for="e in depEdges" :key="e.id">
              <td>
                <span class="mono" style="font-size:11.5px">{{ nodeName(e.source) }}</span>
                <span style="color:var(--text-3);margin:0 5px">→</span>
                <b>{{ nodeName(e.target) }}</b>
              </td>
              <td>
                <label class="sw-row">
                  <input type="checkbox" :checked="!!e.partial" :disabled="!auth.canEdit" @change="togglePartial(e, $event)" />
                  <span class="pill" :class="e.partial ? 'warn' : 'info'">{{ e.partial ? '部分结果数据' : '全量' }}</span>
                </label>
              </td>
              <td>
                <div v-if="e.partial" class="dep-cfg">
                  <div class="dep-row">
                    <span class="dep-k">① 结果表</span>
                    <select class="dep-in" :value="e.partial.table" :disabled="!auth.canEdit" @change="onTable(e, $event)">
                      <option v-for="t in tableOptions" :key="t" :value="t">{{ t }}</option>
                    </select>
                  </div>
                  <div class="dep-row">
                    <span class="dep-k">② 字段子集</span>
                    <input
                      class="dep-in" :value="fieldsText(e)" :disabled="!auth.canEdit"
                      placeholder="逗号分隔，留空 = 全字段，如 order_id,pay_amount"
                      @input="setFields(e, ($event.target as HTMLInputElement).value)"
                    />
                  </div>
                  <div class="dep-row">
                    <span class="dep-k">③ 行过滤</span>
                    <input
                      class="dep-in" :value="e.partial.filter" :disabled="!auth.canEdit"
                      placeholder="过滤表达式，留空 = 全部行，如 status = 'PAID' AND dt = '${biz_date}'"
                      @input="onFilter(e, $event)"
                    />
                  </div>
                  <div class="dep-row">
                    <span class="dep-k">依赖条件</span>
                    <select class="dep-in" style="max-width:180px" :value="e.partial.scope" :disabled="!auth.canEdit" @change="onScope(e, $event)">
                      <option value="cycle">同周期</option>
                      <option value="batch">同批次</option>
                      <option value="cycle_batch">同周期+同批次</option>
                    </select>
                  </div>
                </div>
                <span v-else style="font-size:11.5px;color:var(--text-3)">{{ partialDesc(e) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">当前工作流暂无依赖边，请先在「设计」页签连接节点</div>
        <div class="dep-tip">配置随版本保存；运行时下游节点按字段子集 + 行过滤拉取上游产出，Quality Gate 类节点可在此之上做放行/阻断判定。</div>
      </div>
    </div>

    <!-- 运行：实例列表 -->
    <div v-if="tab === 'runs'" class="wbt-page">
      <div class="card panel">
        <div class="dep-head">
          <div>
            <div class="dep-title">运行实例 — {{ doc?.name ?? docId }}</div>
            <div class="dep-desc">调度与补数实例（含节点状态）；试运行请在「设计」页签发起</div>
          </div>
          <span class="pill info">{{ instances.length }} 条</span>
        </div>
        <table v-if="instances.length" class="tbl">
          <thead>
            <tr><th>实例</th><th>业务日期</th><th>状态</th><th>开始</th><th>结束</th><th>时长</th><th>执行节点</th><th>节点状态</th></tr>
          </thead>
          <tbody>
            <tr v-for="i in instances" :key="i.id">
              <td><span class="mono" style="font-size:11.5px">{{ i.id }}</span></td>
              <td class="mono" style="font-size:11px">{{ i.bizDate }}</td>
              <td><span class="st" :class="stCls(i.status)"><span class="dot" />{{ stLabel(i.status) }}</span></td>
              <td class="mono" style="font-size:11px">{{ i.startAt }}</td>
              <td class="mono" style="font-size:11px">{{ i.endAt }}</td>
              <td>{{ i.dur }}</td>
              <td>
                <span v-if="i.execNode" class="pill info">{{ i.execNode }}</span>
                <span v-else style="color:var(--text-3)">-</span>
              </td>
              <td>
                <div style="display:flex;gap:4px;flex-wrap:wrap">
                  <span v-for="n in i.nodes" :key="n.id" class="pill" :class="nStatusCls(n.status)" :title="`${n.name} ${n.dur}`">{{ n.name }}</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无运行实例（可在「设计」页签试运行，或由调度触发后在此查看）</div>
      </div>
    </div>

    <!-- 日志 -->
    <div v-if="tab === 'logs'" class="wbt-page">
      <div class="card panel">
        <div class="dep-head">
          <div class="dep-title">运行日志</div>
        </div>
        <div class="log-wrap">
          <LogPanel />
        </div>
      </div>
    </div>

    <!-- 变量：工作流变量管理（管理与使用分离） -->
    <div v-if="tab === 'vars'" class="wbt-page">
      <div class="card panel" style="padding:0">
        <WfVarPanel :doc-id="docId" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.wbt{display:flex;flex-direction:column;height:100%}
.wbt-tabs{display:flex;align-items:center;gap:4px;padding:8px 14px 0;background:#fff;border-bottom:1px solid var(--border);flex-shrink:0}
.wbt-tab{border:none;background:none;padding:8px 16px;font-size:13px;color:var(--text-2);cursor:pointer;border-bottom:2px solid transparent;display:flex;align-items:center;gap:6px}
.wbt-tab:hover{color:var(--primary)}
.wbt-tab.on{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}
.wbt-ic{font-size:12px}
.wbt-design{flex:1;min-height:0}
.wbt-page{flex:1;min-height:0;overflow:auto;padding:14px}
.panel{padding:14px 16px}
.dep-head{display:flex;align-items:flex-start;gap:10px;margin-bottom:12px}
.dep-title{font-weight:700;font-size:14px}
.dep-desc{font-size:12px;color:var(--text-2);margin-top:3px}
.pill{display:inline-flex;align-items:center;padding:1px 9px;border-radius:var(--radius-lg);font-size:11px;font-weight:500;white-space:nowrap}
.pill.info{background:var(--info-bg);color:var(--info)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.off{background:var(--bg);color:var(--text-3)}
.pill.ok{background:var(--success-bg);color:var(--success)}
.pill.err{background:rgba(229,72,77,.1);color:var(--danger)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;font-weight:600;color:var(--text-3);font-size:11.5px;padding:7px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.tbl td{padding:9px 8px;border-bottom:1px solid var(--border);vertical-align:top}
.tbl tbody tr:hover{background:var(--bg)}
.empty{padding:28px;text-align:center;color:var(--text-3);font-size:12.5px}
.mono{font-family:ui-monospace,Consolas,monospace}
.sw-row{display:flex;align-items:center;gap:6px;cursor:pointer}
.dep-cfg{display:flex;flex-direction:column;gap:6px}
.dep-row{display:flex;align-items:center;gap:8px}
.dep-k{width:76px;flex-shrink:0;font-size:11.5px;color:var(--text-3)}
.dep-in{flex:1;max-width:460px;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:4px 8px;font-size:12px;outline:none;background:#fff;color:var(--text)}
.dep-in:focus{border-color:var(--primary)}
.dep-tip{background:var(--info-bg);color:var(--info);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px;margin-top:12px}
.log-wrap{max-height:60vh;overflow:auto;padding:10px 4px}
</style>
