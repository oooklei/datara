<script setup lang="ts">
/**
 * WorkflowGraphWorkbench（INC4-FE-6 ③，4.3 画布内核）：vue-flow 画布替换
 * CanvasPlaceholder，接驳 workflowGraph store（FE-6 ② loadSeq/dirty/差量保存）。
 *
 * 同步策略（非受控 + 单向 prop 同步 + 事件选择性回写，无双源）：
 *  - :nodes/:edges 从 store computed 映射单向传入（vue-flow 内部 merge）；
 *  - @connect → store.addEdge（自带自环/幂等守卫；不调 vue-flow addEdges，
 *    边靠 prop 同步进内部态）；
 *  - @nodes-change：remove → removeNode；position 且 !dragging（拖拽落定）
 *    → moveNode（中间态不回写，保 diff 感知）；dimensions/select 忽略；
 *  - @edges-change：remove → 按 EdgeRemoveChange.source/target 直取 removeEdge
 *    （vue-flow 1.48 类型实锚，免 id 解析）。
 *
 * 生命周期（单例 store × 多 Tab KeepAlive 并存，快照兜底）：
 *  - onActivated 为 load 唯一入口（KeepAlive 首挂载也触发 activated）：
 *    projectId 缺位 → 降级注记；同 Tab 复活且 store 仍持 doc → 仅清陈旧快照键
 *    （不重载保编辑态）；否则 load + 快照 $patch 恢复（isDirty 随之）；
 *  - onDeactivated/onUnmounted → dirty 时写 localStorage 快照
 *    datara.dag.snap.${docId}（TaskCenterView onCloseTab hasSnapDraft 同键）；
 *    不 close store——槽位由下一 Tab 的 load 接管。
 *
 * 类型实锚：@vue-flow/core 1.48.2 dist/types（NodeChange/EdgeChange/Connection/
 * MarkerType.ArrowClosed/NodeMouseEvent/EdgeMouseEvent；index.d.ts export * from './types'）。
 */
import { computed, onActivated, onDeactivated, onUnmounted, ref } from 'vue'
import { MarkerType, VueFlow } from '@vue-flow/core'
import type {
  Connection,
  EdgeChange,
  EdgeMouseEvent,
  NodeChange,
  NodeMouseEvent,
} from '@vue-flow/core'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { DagTab } from '../stores/dagTabs'
import {
  WF_NODE_TYPES,
  listWorkflowVersions,
  publishWorkflowDefinition,
  type WorkflowDraftEdge,
  type WorkflowDraftNode,
  type WorkflowVersion,
  type WfNodeType,
} from '../services/rebuild/workflowApi'
import { useWorkflowGraphStore } from '../stores/workflowGraph'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

const props = defineProps<{ tab: DagTab; projectId?: number }>()

const graphStore = useWorkflowGraphStore()

/** DagTab.docId（string）→ store docId（number）桥 */
const numDocId = computed(() => Number(props.tab.docId))

const degraded = ref(props.projectId === undefined)
const loading = ref(false)
const loaded = ref(false)

/* ---------- store → vue-flow 单向映射 ---------- */

const flowNodes = computed(() =>
  graphStore.nodes.map((n: WorkflowDraftNode) => ({
    id: n.nodeCode,
    type: 'default',
    position: { x: n.positionX ?? 0, y: n.positionY ?? 0 },
    label: `${n.nodeCode} ${n.nodeType}${n.name ? ` ${n.name}` : ''}`,
  })),
)

const flowEdges = computed(() =>
  graphStore.edges.map((e: WorkflowDraftEdge) => ({
    id: `${e.fromNode}->${e.toNode}`,
    source: e.fromNode,
    target: e.toNode,
    label: e.name ?? undefined,
    markerEnd: MarkerType.ArrowClosed,
  })),
)

/* ---------- vue-flow → store 选择性回写 ---------- */

function onConnect(conn: Connection) {
  graphStore.addEdge(conn.source, conn.target)
}

function onNodesChange(changes: NodeChange[]) {
  for (const c of changes) {
    if (c.type === 'remove') {
      graphStore.removeNode(c.id)
    } else if (c.type === 'position' && !c.dragging) {
      graphStore.moveNode(c.id, c.position.x, c.position.y)
    }
  }
}

function onEdgesChange(changes: EdgeChange[]) {
  for (const c of changes) {
    if (c.type === 'remove') graphStore.removeEdge(c.source, c.target)
  }
}

/* ---------- 选中态（工具栏删除） ---------- */

const selectedNode = ref<string | null>(null)
const selectedEdge = ref<{ from: string; to: string } | null>(null)

function onNodeClick({ node }: NodeMouseEvent) {
  selectedNode.value = node.id
  selectedEdge.value = null
}
function onEdgeClick({ edge }: EdgeMouseEvent) {
  selectedNode.value = null
  selectedEdge.value = { from: edge.source, to: edge.target }
}
function clearSelection() {
  selectedNode.value = null
  selectedEdge.value = null
}
function onDeleteSelected() {
  if (selectedNode.value) {
    graphStore.removeNode(selectedNode.value)
    clearSelection()
  } else if (selectedEdge.value) {
    graphStore.removeEdge(selectedEdge.value.from, selectedEdge.value.to)
    clearSelection()
  }
}

/* ---------- 托盘（13 类型点击加节点，级联摆位） ---------- */

function onAddNode(t: WfNodeType) {
  const n = graphStore.nodes.length
  graphStore.addNode({
    nodeType: t,
    positionX: 24 + (n % 6) * 48,
    positionY: 24 + Math.floor(n / 6) * 48,
  })
}

/* ---------- 快照（localStorage，键与 TaskCenterView hasSnapDraft 约定一致） ---------- */

function snapKey(): string {
  return `datara.dag.snap.${props.tab.docId}`
}

function readSnap(): { nodes: WorkflowDraftNode[]; edges: WorkflowDraftEdge[] } | null {
  try {
    const raw = localStorage.getItem(snapKey())
    if (!raw) return null
    const s = JSON.parse(raw) as { draft?: { nodes?: WorkflowDraftNode[]; edges?: WorkflowDraftEdge[] } }
    return s?.draft && Array.isArray(s.draft.nodes) && Array.isArray(s.draft.edges)
      ? { nodes: s.draft.nodes, edges: s.draft.edges }
      : null
  } catch {
    return null
  }
}

function clearSnap() {
  localStorage.removeItem(snapKey())
}

function persistSnap() {
  if (graphStore.docId !== numDocId.value || !graphStore.isDirty) return
  // reactive 数组深拷贝（structuredClone 对 Proxy 会抛错，JSON 序列化沿 store 惯例）
  const payload = {
    draft: {
      nodes: JSON.parse(JSON.stringify(graphStore.nodes)) as WorkflowDraftNode[],
      edges: JSON.parse(JSON.stringify(graphStore.edges)) as WorkflowDraftEdge[],
    },
  }
  try {
    localStorage.setItem(snapKey(), JSON.stringify(payload))
  } catch {
    // 配额满不阻断停用流程（TaskCenterView 关闭三选已有草稿提示兜底）
  }
}

/* ---------- 生命周期（KeepAlive） ---------- */

async function ensureLoaded() {
  if (props.projectId === undefined) {
    degraded.value = true
    return
  }
  degraded.value = false
  if (graphStore.docId === numDocId.value) {
    // 同 Tab 复活：store 仍持 doc（不 close on deactivate），清陈旧快照键即可
    clearSnap()
    return
  }
  loading.value = true
  try {
    await graphStore.load(props.projectId, numDocId.value)
    const snap = readSnap()
    if (snap) {
      // 直接状态赋值（$patch 的 _DeepPartial 对 Record<string, unknown> 索引签名不兼容）
      graphStore.nodes = snap.nodes
      graphStore.edges = snap.edges
      clearSnap()
    }
    loaded.value = true
  } catch {
    ElMessage.error('画布数据加载失败')
  } finally {
    loading.value = false
  }
}

onActivated(() => {
  void ensureLoaded()
})
onDeactivated(() => persistSnap())
onUnmounted(() => persistSnap())

/* ---------- 工具栏：保存 / 发布 / 版本 ---------- */

async function onSave() {
  const r = await graphStore.save()
  if (!r) {
    ElMessage.warning('画布未加载，无法保存')
    return
  }
  if (r.complete) {
    ElMessage.success('保存成功')
    return
  }
  ElMessage.error(`保存未完成：${r.dirtyKeys.join(', ')}`)
}

async function onPublish() {
  if (props.projectId === undefined) return
  let remark: string | undefined
  try {
    const p = await ElMessageBox.prompt('输入版本备注（可选）', '发布版本', {
      confirmButtonText: '发布',
      cancelButtonText: '取消',
      inputPlaceholder: '备注',
    })
    const v = (p.value ?? '').trim()
    remark = v || undefined
  } catch {
    return
  }
  try {
    const ver = await publishWorkflowDefinition(props.projectId, numDocId.value, remark)
    ElMessage.success(`已发布版本 v${ver.version}`)
  } catch {
    ElMessage.error('发布失败')
  }
}

const versionsVisible = ref(false)
const versions = ref<WorkflowVersion[]>([])

async function onShowVersions() {
  if (props.projectId === undefined) return
  try {
    versions.value = await listWorkflowVersions(props.projectId, numDocId.value)
    versionsVisible.value = true
  } catch {
    ElMessage.error('版本列表加载失败')
  }
}
</script>

<template>
  <div class="wf-workbench" data-tc-canvas-workbench>
    <div class="wf-toolbar">
      <div class="wf-actions">
        <button class="wf-btn" :disabled="!loaded" @click="onSave">保存</button>
        <button
          class="wf-btn"
          :disabled="!loaded || (!selectedNode && !selectedEdge)"
          title="删除选中节点/连线"
          @click="onDeleteSelected"
        >删除选中</button>
        <button class="wf-btn" :disabled="degraded || !loaded" @click="onPublish">发布</button>
        <button class="wf-btn" :disabled="degraded || !loaded" @click="onShowVersions">版本</button>
        <span
          v-if="graphStore.docId === numDocId && graphStore.isDirty"
          class="wf-dirty"
          title="存在未保存的修改"
        >未保存</span>
      </div>
      <div class="wf-tray">
        <button
          v-for="t in WF_NODE_TYPES"
          :key="t"
          class="wf-type"
          :disabled="!loaded"
          @click="onAddNode(t)"
        >{{ t }}</button>
      </div>
    </div>

    <div v-if="degraded" class="wf-degraded">画布：{{ tab.name }}（无项目上下文，待接驳）</div>
    <div v-else-if="loading" class="wf-degraded">画布加载中…</div>
    <div v-else-if="!loaded" class="wf-degraded">画布：{{ tab.name }}</div>
    <div v-else class="wf-flow">
      <VueFlow
        :nodes="flowNodes"
        :edges="flowEdges"
        :apply-default="true"
        @connect="onConnect"
        @nodes-change="onNodesChange"
        @edges-change="onEdgesChange"
        @node-click="onNodeClick"
        @edge-click="onEdgeClick"
        @pane-click="clearSelection"
      >
        <Controls />
        <MiniMap pannable zoomable />
      </VueFlow>
    </div>

    <el-dialog v-model="versionsVisible" title="版本历史" width="640px" append-to-body>
      <el-table :data="versions" size="small">
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="remark" label="备注" />
        <el-table-column prop="publishedAt" label="发布时间" width="170" />
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 根布局 flex column：工具栏（动作行 + 托盘行）+ 流容器 flex:1（VueFlow 需显式高度） */
.wf-workbench {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
}
.wf-toolbar {
  flex-shrink: 0;
  border-bottom: 1px solid var(--border-color, #e2e8f0);
  background: var(--bg-secondary, #f8fafc);
}
.wf-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
}
.wf-btn {
  border: 1px solid var(--border-color, #e2e8f0);
  background: #fff;
  border-radius: var(--radius-sm, 6px);
  padding: 4px 12px;
  font-size: 12.5px;
  color: var(--text-primary, #1e293b);
  cursor: pointer;
}
.wf-btn:hover:not(:disabled) {
  border-color: var(--primary-color, #2563eb);
  color: var(--primary-color, #2563eb);
}
.wf-btn:disabled {
  color: var(--text-4, #cbd5e1);
  cursor: not-allowed;
}
.wf-dirty {
  font-size: 11.5px;
  color: var(--warning, #d97706);
  background: var(--warning-bg, #fef3c7);
  border-radius: 8px;
  padding: 1px 8px;
}
.wf-tray {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 10px 8px;
}
.wf-type {
  border: 1px solid var(--border-color, #e2e8f0);
  background: #fff;
  border-radius: var(--radius-sm, 6px);
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-secondary, #64748b);
  cursor: pointer;
}
.wf-type:hover:not(:disabled) {
  border-color: var(--primary-color, #2563eb);
  color: var(--primary-color, #2563eb);
  background: var(--primary-light, #eff6ff);
}
.wf-type:disabled {
  color: var(--text-4, #cbd5e1);
  cursor: not-allowed;
}
.wf-degraded {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-3, #94a3b8);
  font-size: 13px;
}
.wf-flow {
  flex: 1;
  min-height: 0;
}
.wf-flow :deep(.vue-flow) {
  height: 100%;
}
</style>
