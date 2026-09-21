<script setup lang="ts">
/**
 * I7 C9 依赖项列表编辑器（设计文档 §3.2）：
 * 每行 = 工作流下拉（real 走 listDefinitions，mock 用 seedWorkflows）
 * + 节点下拉（随工作流定义级联：graphService.get 拉 GraphDocument 节点清单，按 wf 缓存）
 * + 可选变量条件表达式（如 wf.period=${wf.period}）。
 * 行存储 {wf, node, cond, wfName?, nodeName?}：wf/node 为稳定 id（后端按 id 解析定义与最近实例节点状态），
 * 名称仅摘要与日志可读。当前文档自身不进工作流下拉（防自依赖成环，DAG 校验器兜底）。
 */
import { onMounted, ref } from 'vue'
import { graphService, isMock, listDefinitions } from '../../../services'
import { seedWorkflows } from '../../../services/mock/seed'
import type { DependentDef } from '../../../graph/profiles/types'

const props = defineProps<{
  rows: { [k: string]: unknown }[]
  /** 当前文档 id（下拉中排除，防自依赖） */
  excludeId?: string
  disabled?: boolean
}>()
const emit = defineEmits<{ (e: 'change'): void }>()

const rowList = () => props.rows as unknown as DependentDef[]

/* ---------- 工作流下拉（once） ---------- */
const defs = ref<{ id: string; name: string }[]>([])
const defOpts = () => defs.value.filter((d) => !props.excludeId || d.id !== props.excludeId)

/* ---------- 节点级联（按 wf 缓存） ---------- */
type NodeOpt = { id: string; name: string; type: string }
const nodeCache = ref<Record<string, NodeOpt[]>>({})
const nodeLoading = ref<Record<string, boolean>>({})
function nodeOpts(wf: string): NodeOpt[] {
  return nodeCache.value[wf] ?? []
}
async function loadNodes(wf: string) {
  if (!wf || nodeCache.value[wf] || nodeLoading.value[wf]) return
  nodeLoading.value[wf] = true
  try {
    const doc = await graphService.get(wf)
    nodeCache.value[wf] = (doc?.nodes ?? []).map((n) => ({
      id: n.id,
      name: String((n.data as { name?: unknown })?.name ?? n.id),
      type: n.type,
    }))
    /* 级联到达后为已有行回填节点展示名 */
    for (const r of rowList()) backfillNodeName(r)
  } catch { /* 定义不可达时节点下拉留空 */ }
  finally { nodeLoading.value[wf] = false }
}

function backfillName(r: DependentDef) {
  if (!r.wfName) r.wfName = defs.value.find((d) => d.id === r.wf)?.name
}
function backfillNodeName(r: DependentDef) {
  if (!r.nodeName) r.nodeName = nodeOpts(r.wf).find((n) => n.id === r.node)?.name
}

onMounted(async () => {
  try {
    defs.value = isMock
      ? seedWorkflows.map((w) => ({ id: w.id, name: w.name }))
      : (await listDefinitions({ pageSize: 200 })).map((d) => ({ id: d.id, name: d.name }))
  } catch { /* 后端未就绪：下拉留空不阻断表单 */ }
  for (const r of rowList()) {
    if (!r.wf) continue
    backfillName(r)
    void loadNodes(r.wf)
  }
})

/* ---------- 行编辑 ---------- */
function setWf(r: DependentDef, ev: Event) {
  r.wf = (ev.target as HTMLSelectElement).value
  r.node = ''
  r.nodeName = undefined
  r.wfName = defs.value.find((d) => d.id === r.wf)?.name
  void loadNodes(r.wf)
  emit('change')
}
function setNode(r: DependentDef, ev: Event) {
  r.node = (ev.target as HTMLSelectElement).value
  r.nodeName = nodeOpts(r.wf).find((n) => n.id === r.node)?.name
  emit('change')
}
function setCond(r: DependentDef, ev: Event) {
  r.cond = (ev.target as HTMLInputElement).value
  emit('change')
}
function addRow() {
  props.rows.push({ wf: '', node: '', cond: '' })
  emit('change')
}
function delRow(i: number) {
  props.rows.splice(i, 1)
  emit('change')
}
</script>

<template>
  <div class="depsf">
    <table class="depsf-tbl">
      <thead>
        <tr><th>依赖工作流</th><th>依赖节点</th><th>变量条件（可选）</th><th class="depsf-op"></th></tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rowList()" :key="i">
          <td>
            <select :value="String(r.wf ?? '')" :disabled="disabled" @change="setWf(r, $event)">
              <option value="">请选择工作流…</option>
              <option v-for="d in defOpts()" :key="d.id" :value="d.id">{{ d.name }}</option>
            </select>
          </td>
          <td>
            <select :value="String(r.node ?? '')" :disabled="disabled || !r.wf" @change="setNode(r, $event)">
              <option value="">{{ r.wf ? (nodeLoading[r.wf] ? '加载节点中…' : '请选择节点…') : '先选工作流' }}</option>
              <option v-for="n in nodeOpts(String(r.wf ?? ''))" :key="n.id" :value="n.id">{{ n.name }}（{{ n.type }}）</option>
            </select>
          </td>
          <td>
            <input :value="String(r.cond ?? '')" :disabled="disabled" placeholder="如 wf.period=${wf.period}" @change="setCond(r, $event)" />
          </td>
          <td class="depsf-op"><button :disabled="disabled" title="删除该依赖项" @click="delRow(i)">×</button></td>
        </tr>
        <tr v-if="!rows.length"><td colspan="4" class="depsf-empty">暂无依赖项</td></tr>
      </tbody>
    </table>
    <button v-if="!disabled" class="depsf-add" @click="addRow">＋ 新增依赖项</button>
    <div class="depsf-hint">判定口径：所配依赖各自「最近一次实例」中该节点终态=success 即通过；变量条件在节点成功基础上追加匹配</div>
  </div>
</template>

<style scoped>
.depsf-tbl{width:100%;border-collapse:collapse;font-size:11px}
.depsf-tbl th{text-align:left;font-weight:600;color:var(--text-3);padding:2px 3px;border-bottom:1px solid var(--border)}
.depsf-tbl td{padding:2px 3px;border-bottom:1px dashed var(--border)}
.depsf-tbl input,.depsf-tbl select{width:100%;min-width:0;border:1px solid var(--border);border-radius:var(--radius-sm);padding:3px 5px;font-size:11px;outline:none}
.depsf-tbl input:focus,.depsf-tbl select:focus{border-color:var(--primary)}
.depsf-op{width:20px}
.depsf-op button{width:18px;height:18px;border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);color:var(--text-3);font-size:11px;line-height:1;cursor:pointer}
.depsf-op button:hover:not(:disabled){border-color:var(--danger);color:var(--danger)}
.depsf-op button:disabled{opacity:.4;cursor:not-allowed}
.depsf-empty{text-align:center;color:var(--text-3);padding:6px 0;font-size:11px}
.depsf-add{margin-top:4px;width:100%;border:1px dashed var(--border-strong);background:var(--bg);border-radius:var(--radius-sm);padding:4px 0;font-size:11px;color:var(--text-2);cursor:pointer}
.depsf-add:hover{border-color:var(--primary);color:var(--primary)}
.depsf-hint{font-size:10.5px;color:var(--text-3);margin-top:4px}
</style>
