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
  listWorkflowVersions,
  publishWorkflowDefinition,
  type WorkflowDraftEdge,
  type WorkflowDraftNode,
  type WorkflowVersion,
  type WfNodeType,
} from '../services/rebuild/workflowApi'
import { isDesignComponent, loadComponentSpecs, type ComponentSpecItem, type WorkflowType } from '../services/rebuild/componentSpecApi'
import { useWorkflowGraphStore } from '../stores/workflowGraph'
import WorkflowVariablePanel from './WorkflowVariablePanel.vue'
import ScriptResourceEditor from './ScriptResourceEditor.vue'
import StreamObservationPanel from './StreamObservationPanel.vue'
import SyncMappingEditor from './SyncMappingEditor.vue'
import { createDependencyContract } from '../services/rebuild/dependencyApi'

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

const props = defineProps<{ tab: DagTab; projectId?: number }>()

const graphStore = useWorkflowGraphStore()
const variablesVisible = ref(false)

/** DagTab.docId（string）→ store docId（number）桥 */
const numDocId = computed(() => Number(props.tab.docId))

const degraded = ref(props.projectId === undefined)
const loading = ref(false)
const loaded = ref(false)
const availableComponents = ref<ComponentSpecItem[]>([])
const workflowType = computed<WorkflowType>(() => props.tab.type === 'sync' ? 'SYNC' : props.tab.type === 'stream' ? 'STREAM' : 'NORMAL')

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
const selectedNodeRecord = computed(() => graphStore.nodes.find((node) => node.nodeCode === selectedNode.value) ?? null)
const nodeParameterKey = computed(() => {
  const type = String(selectedNodeRecord.value?.nodeType ?? '').toLowerCase()
  if (type === 'sql') return 'sql'
  if (type === 'python' || type === 'shell') return 'script'
  return null
})
const scriptResourceKind = computed(() => {
  const type = String(selectedNodeRecord.value?.nodeType ?? '').toLowerCase()
  return type === 'sql' || type === 'python' || type === 'shell' ? type : null
})
function updateNodeParams(value: Record<string, unknown>) {
  const node = selectedNodeRecord.value
  if (!node) return
  graphStore.updateNode(node.nodeCode, { params: value })
}
const isSyncMappingNode = computed(() => workflowType.value === 'SYNC' && Boolean(selectedNodeRecord.value?.nodeType && ['endpoint_select', 'field_map', 'field_map_union', 'src_base_orch', 'tgt_base_orch', 'file_sync_orch'].includes(String(selectedNodeRecord.value?.nodeType).toLowerCase())))
const isDependentNode = computed(() => String(selectedNodeRecord.value?.nodeType ?? '').toLowerCase() === 'dependent')
const dependencySaving = ref(false)
const dependencySaved = ref(false)
function dependentValue(key: string, fallback: string | number = ''): string | number {
  return selectedNodeRecord.value?.params?.[key] as string | number ?? fallback
}
function updateDependentParam(key: string, value: string | number) {
  const node = selectedNodeRecord.value
  if (!node) return
  graphStore.updateNode(node.nodeCode, { params: { ...(node.params ?? {}), [key]: value } })
}
async function saveDependencyConfig() {
  const node = selectedNodeRecord.value
  if (!node || props.projectId === undefined) return
  const p = node.params ?? {}
  const dependencyId = Number(p.dependency_id)
  if (!Number.isInteger(dependencyId) || dependencyId <= 0) {
    ElMessage.warning('请先填写有效的依赖标识')
    return
  }
  dependencySaving.value = true
  dependencySaved.value = false
  try {
    const selector = String(p.dependent_execute ?? 'workflow') as 'workflow' | 'all_tasks' | 'task'
    const taskCode = selector === 'workflow' ? '0' : selector === 'all_tasks' ? '-1' : String(p.upstream_task_code ?? '')
    if (selector === 'task' && (!/^\d+$/.test(taskCode) || Number(taskCode) <= 0)) {
      ElMessage.warning('指定任务依赖需要填写正整数任务编码')
      return
    }
    await createDependencyContract().saveDependency({
      projectId: props.projectId,
      workflowId: numDocId.value,
      workflowVersion: 1,
      taskId: node.nodeCode,
      groupRelation: String(p.group_relation ?? 'AND') === 'OR' ? 'OR' : 'AND',
      checkIntervalSeconds: Number(p.check_interval_seconds ?? 10),
      failurePolicy: String(p.failure_policy ?? 'fail') === 'waiting' ? 'waiting' : 'fail',
      ...(String(p.failure_policy ?? 'fail') === 'waiting' ? { failureWaitingSeconds: Number(p.failure_waiting_seconds ?? 60) } : {}),
      timeoutSeconds: Number(p.timeout_seconds ?? 30),
      groups: [{
        join: String(p.relation ?? 'AND') === 'OR' ? 'OR' : 'AND',
        conditions: [{
          kind: selector === 'workflow' ? 'workflow' : 'task',
          selector,
          upstreamWorkflowId: dependencyId,
          upstreamTaskCode: taskCode,
          cycle: String(p.cycle ?? 'day') as 'hour' | 'day' | 'week' | 'month',
          dateValue: String(p.date_value ?? 'last1Days'),
          dependResult: String(p.depend_result ?? 'success') === 'failed' ? 'failed' : 'success',
          parameterPassing: Boolean(p.parameter_passing ?? false),
        }],
      }],
    })
    dependencySaved.value = true
    ElMessage.success('依赖配置已保存')
  } catch (error) {
    ElMessage.error(`依赖配置保存失败：${error instanceof Error ? error.message : '请求异常'}`)
  } finally {
    dependencySaving.value = false
  }
}
function updateSyncParams(value: Record<string, unknown>) {
  const node = selectedNodeRecord.value
  if (node) graphStore.updateNode(node.nodeCode, { params: { ...(node.params ?? {}), ...value } })
}

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

function onAddNode(component: ComponentSpecItem) {
  const n = graphStore.nodes.length
  graphStore.addNode({
    nodeType: component.type as WfNodeType,
    componentRef: component.componentRef,
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
  try {
    availableComponents.value = (await loadComponentSpecs(workflowType.value)).items
      .filter((item) => isDesignComponent(item, workflowType.value))
  } catch {
    availableComponents.value = []
    ElMessage.error('组件目录加载失败')
    return
  }
  // Definition ids are only unique within a project.  When a keep-alive
  // project route changes, the same numeric workflow id must be reloaded
  // instead of reusing the previous project's draft.
  if (graphStore.docId === numDocId.value && graphStore.projectId === props.projectId) {
    // 同 Tab 复活：store 仍持 doc（不 close on deactivate），清陈旧快照键即可
    clearSnap()
    return
  }
  loaded.value = false
  loading.value = true
  try {
    await graphStore.load(props.projectId, numDocId.value)
    // load() records transport errors on the store instead of throwing so
    // callers can keep the shared store alive.  Do not mark the canvas ready
    // when that happened: otherwise Save/Publish become enabled for an empty
    // graph and can overwrite a draft after a transient read failure.
    if (graphStore.docId !== numDocId.value || graphStore.lastError) {
      loaded.value = false
      ElMessage.error(`画布数据加载失败：${graphStore.lastError ?? '未返回工作流草稿'}`)
      return
    }
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
  let r
  try {
    r = await graphStore.save()
  } catch (error) {
    ElMessage.error(`保存失败：${error instanceof Error ? error.message : '请求异常'}`)
    return
  }
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
  // Publishing a stale server draft is a destructive surprise.  Flush local
  // graph changes first and stop when the queue reports partial failure.
  if (graphStore.isDirty) {
    try {
      const saved = await graphStore.save()
      if (!saved?.complete) {
        ElMessage.error(`发布前保存未完成：${saved?.dirtyKeys.join(', ') ?? '未知变更'}`)
        return
      }
    } catch (error) {
      ElMessage.error(`发布前保存失败：${error instanceof Error ? error.message : '请求异常'}`)
      return
    }
  }
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
  } catch (error) {
    ElMessage.error(`发布失败：${error instanceof Error ? error.message : '请求异常'}`)
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
        <button class="wf-btn" data-workflow-variables :disabled="degraded || !loaded" @click="variablesVisible = true">工作流变量</button>
        <span
          v-if="graphStore.docId === numDocId && graphStore.isDirty"
          class="wf-dirty"
          title="存在未保存的修改"
        >未保存</span>
      </div>
      <div class="wf-tray">
        <button
          v-for="component in availableComponents"
          :key="component.type"
          class="wf-type"
          :disabled="!loaded"
          @click="onAddNode(component)"
        >{{ component.identity.displayName ?? component.type }}</button>
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

    <section v-if="selectedNodeRecord && nodeParameterKey" class="node-editor" data-node-parameter-editor>
      <strong>{{ selectedNodeRecord.nodeType }} 参数 · {{ selectedNodeRecord.nodeCode }}</strong>
      <ScriptResourceEditor
        v-if="projectId !== undefined && scriptResourceKind"
        :key="selectedNodeRecord.nodeCode"
        :project-id="projectId"
        :workflow-id="numDocId"
        :workflow-version="1"
        :task-id="selectedNodeRecord.nodeCode"
        :kind="scriptResourceKind"
        :model-value="selectedNodeRecord.params ?? {}"
        @update:model-value="updateNodeParams"
      />
    </section>
    <section v-if="selectedNodeRecord && isDependentNode" class="node-editor dependency-editor" data-dependent-editor>
      <strong>依赖组件参数 · {{ selectedNodeRecord.nodeCode }}</strong>
      <label>执行范围<select :value="dependentValue('dependent_execute', 'workflow')" @change="updateDependentParam('dependent_execute', ($event.target as HTMLSelectElement).value)">
        <option value="workflow">整工作流</option><option value="all_tasks">全部任务</option><option value="task">指定任务</option>
      </select></label>
      <label>依赖类型
        <select :value="dependentValue('kind', 'workflow')" disabled title="文件/表状态/外部任务的详细契约尚未冻结">
          <option value="workflow">工作流/任务</option>
        </select>
      </label>
      <label>依赖标识<input :value="dependentValue('dependency_id')" @input="updateDependentParam('dependency_id', ($event.target as HTMLInputElement).value)" /></label>
      <label v-if="dependentValue('dependent_execute', 'workflow') === 'task'">任务编码<input :value="dependentValue('upstream_task_code')" @input="updateDependentParam('upstream_task_code', ($event.target as HTMLInputElement).value)" /></label>
      <label>组内关系<select :value="dependentValue('relation', 'AND')" @change="updateDependentParam('relation', ($event.target as HTMLSelectElement).value)"><option>AND</option><option>OR</option></select></label>
      <label>组间关系<select :value="dependentValue('group_relation', 'AND')" @change="updateDependentParam('group_relation', ($event.target as HTMLSelectElement).value)"><option>AND</option><option>OR</option></select></label>
      <label>时间周期<select :value="dependentValue('cycle', 'day')" @change="updateDependentParam('cycle', ($event.target as HTMLSelectElement).value)"><option value="hour">小时</option><option value="day">天</option><option value="week">周</option><option value="month">月</option></select></label>
      <label>命名窗口<input :value="dependentValue('date_value', 'last1Days')" @input="updateDependentParam('date_value', ($event.target as HTMLInputElement).value)" /></label>
      <label>期望结果<select :value="dependentValue('depend_result', 'success')" @change="updateDependentParam('depend_result', ($event.target as HTMLSelectElement).value)"><option value="success">成功</option><option value="failed">失败</option></select></label>
      <label>参数透传<input type="checkbox" :checked="Boolean(dependentValue('parameter_passing', 0))" @change="updateDependentParam('parameter_passing', ($event.target as HTMLInputElement).checked ? 1 : 0)" /></label>
      <label>检查周期(秒)<input type="number" min="1" :value="dependentValue('check_interval_seconds', 10)" @input="updateDependentParam('check_interval_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
      <label>超时(秒)<input type="number" min="1" :value="dependentValue('timeout_seconds', 30)" @input="updateDependentParam('timeout_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
      <label>失败策略<select :value="dependentValue('failure_policy', 'fail')" @change="updateDependentParam('failure_policy', ($event.target as HTMLSelectElement).value)"><option value="fail">失败</option><option value="waiting">等待</option></select></label>
      <label v-if="dependentValue('failure_policy', 'fail') === 'waiting'">失败等待(秒)<input type="number" min="1" :value="dependentValue('failure_waiting_seconds', 60)" @input="updateDependentParam('failure_waiting_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
      <button type="button" class="wf-btn dependency-save" :disabled="dependencySaving" @click="saveDependencyConfig">{{ dependencySaving ? '保存中…' : dependencySaved ? '已保存' : '保存依赖配置' }}</button>
    </section>
    <StreamObservationPanel v-if="workflowType === 'STREAM' && loaded" />
    <SyncMappingEditor
      v-if="isSyncMappingNode && projectId !== undefined && selectedNodeRecord"
      :project-id="projectId"
      :workflow-id="numDocId"
      :workflow-version="1"
      :task-id="selectedNodeRecord.nodeCode"
      :model-value="selectedNodeRecord.params ?? {}"
      @update:model-value="updateSyncParams"
    />

    <el-dialog v-model="versionsVisible" title="版本历史" width="640px" append-to-body>
      <el-table :data="versions" size="small">
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="remark" label="备注" />
        <el-table-column prop="publishedAt" label="发布时间" width="170" />
      </el-table>
    </el-dialog>
    <WorkflowVariablePanel
      v-if="projectId !== undefined"
      v-model="variablesVisible"
      :project-id="projectId"
      :workflow-id="numDocId"
    />
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
.node-editor{flex-shrink:0;padding:10px 14px;border-top:1px solid var(--border-color,#e2e8f0);background:#f8fafc;display:grid;gap:6px}
.dependency-editor{grid-template-columns:repeat(3,minmax(130px,1fr));align-items:center}
.dependency-editor strong{grid-column:1/-1}
.dependency-editor label{display:grid;gap:3px;font-size:11px;color:var(--text-secondary,#64748b)}
.dependency-editor input,.dependency-editor select{min-width:0;border:1px solid var(--border-color,#cbd5e1);border-radius:4px;padding:4px 6px;background:#fff;font-size:12px}
.dependency-save{justify-self:start}
</style>
