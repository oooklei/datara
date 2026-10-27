/**
 * INC4-FE-6（WBS 4.4）：workflow 画布编排图 store（draft 权威态 + R-25 差量保存）。
 *
 * 职责（真源：workflowApi 十方法 + workflowSaveQueue R-25 协调器 + 4-O4-04 证据件）：
 *  - load：getWorkflowDefinition 回读 draft → loadSeq 时序守卫（KeepAlive 复活/切 Tab
 *    竞态下仅最新响应落地，过期响应与过期错误一并丢弃）→ baseline 深拷贝锚定；
 *  - 本地编辑 actions：addNode（nodeCode 生成 n{n+1}，取现有 n\\d+ 最大号 +1）/
 *    removeNode（本地级联删触边，与服务端 nodes/delete 级联同语义）/
 *    updateNode/moveNode/addEdge（(from,to) 身份幂等、自环拒绝）/removeEdge；
 *  - isDirty：当前 vs baseline 逐项结构比较（身份集合 + 内容 canonical 序列化，
 *    与数组顺序无关）；
 *  - save：diff（baseline vs 当前）→ WorkflowSaveDelta[] → WorkflowSaveQueue.save。
 *    delta 安全序：删边 → 删节点 → upsert 节点 → upsert 边（边 upsert 要求两端节点
 *    已存在 WF_EDGE_INVALID；nodeCode 复用时 upsert 必须晚于同号删除；节点删除级联
 *    触边造成的重复删边由读回裁定承接——read 回读 null=next 即 saved）。
 *    R-25 部分成功+补偿：write→read 权威读回→equals 裁定；失败项保持 dirty 可重试；
 *    补偿失败 → recovery-failed 不自动重试；complete → baseline 收口 dirty=false。
 *  - close：宿主关 Tab 时若 docId 匹配则清态。
 */
import { defineStore } from 'pinia'

import {
  deleteWorkflowDraftEdge,
  deleteWorkflowDraftNode,
  getWorkflowDefinition,
  upsertWorkflowDraftEdge,
  upsertWorkflowDraftNode,
  type WorkflowDraftEdge,
  type WorkflowDraftNode,
  type WfNodeType,
} from '../services/rebuild/workflowApi'
import {
  WorkflowSaveQueue,
  type WorkflowSaveDelta,
  type WorkflowSaveResult,
} from '../services/rebuild/workflowSaveQueue'

/* ---------- canonical 序列化（身份 + 内容比较，与数组顺序无关） ---------- */

type DraftNodeOrNull = WorkflowDraftNode | null

function serializeNode(n: DraftNodeOrNull): string {
  if (n === null) return 'null'
  return JSON.stringify([n.nodeCode, n.nodeType, n.name, n.params, n.componentRef, n.positionX, n.positionY])
}

function serializeEdge(e: WorkflowDraftEdge | null): string {
  if (e === null) return 'null'
  return JSON.stringify([e.fromNode, e.toNode, e.name])
}

function edgeKey(e: Pick<WorkflowDraftEdge, 'fromNode' | 'toNode'>): string {
  return `${e.fromNode}->${e.toNode}`
}

/** 逐项结构比较：数量/身份集合/单项内容任一差异即 true */
function graphDiffers(
  aNodes: WorkflowDraftNode[],
  aEdges: WorkflowDraftEdge[],
  bNodes: WorkflowDraftNode[],
  bEdges: WorkflowDraftEdge[],
): boolean {
  if (aNodes.length !== bNodes.length || aEdges.length !== bEdges.length) return true
  const nodeMap = new Map(aNodes.map((n) => [n.nodeCode, n]))
  for (const n of bNodes) {
    const prev = nodeMap.get(n.nodeCode)
    if (!prev || serializeNode(prev) !== serializeNode(n)) return true
  }
  const edgeMap = new Map(aEdges.map((e) => [edgeKey(e), e]))
  for (const e of bEdges) {
    const prev = edgeMap.get(edgeKey(e))
    if (!prev || serializeEdge(prev) !== serializeEdge(e)) return true
  }
  return false
}

function snapshot(nodes: WorkflowDraftNode[], edges: WorkflowDraftEdge[]): { nodes: WorkflowDraftNode[]; edges: WorkflowDraftEdge[] } {
  // structuredClone 无法克隆 Vue reactive Proxy；draft 字段均为 JSON 安全值
  // （string/number/null/plain params），且 equals 本就基于 JSON 序列化。
  return JSON.parse(JSON.stringify({ nodes, edges }))
}

function nextNodeCode(nodes: WorkflowDraftNode[]): string {
  let max = 0
  for (const n of nodes) {
    const m = /^n(\d+)$/.exec(n.nodeCode)
    if (m) max = Math.max(max, Number(m[1]))
  }
  return `n${max + 1}`
}

/* ---------- T3 拖边即引用：inputs 派生与清理（nodeId:port 具名引用） ---------- */

/** 组件 spec 未定义 ports 时的默认端口约定：source 端固定 ':out' */
function sourceRefOf(fromNode: string): string {
  return `${fromNode}:out`
}

function inputRefsOf(node: WorkflowDraftNode): Record<string, unknown> {
  const inputs = node.params?.inputs
  return typeof inputs === 'object' && inputs !== null && !Array.isArray(inputs)
    ? { ...(inputs as Record<string, unknown>) }
    : {}
}

function nextInputKey(inputs: Record<string, unknown>): string {
  const keys = new Set(Object.keys(inputs))
  if (!keys.has('in')) return 'in'
  let n = 2
  while (keys.has(`in${n}`)) n += 1
  return `in${n}`
}

function deriveInputRef(nodes: WorkflowDraftNode[], toNode: string, fromNode: string): void {
  const target = nodes.find((n) => n.nodeCode === toNode)
  if (!target) return
  const inputs = inputRefsOf(target)
  inputs[nextInputKey(inputs)] = sourceRefOf(fromNode)
  target.params = { ...(target.params ?? {}), inputs }
}

/** 删除 from→target 触边后回收 target params.inputs 里的悬挂引用（值前缀 nodeId: 匹配） */
function pruneInputRefs(nodes: WorkflowDraftNode[], toNode: string, fromNode: string): void {
  const target = nodes.find((n) => n.nodeCode === toNode)
  if (!target || !target.params) return
  const inputs = inputRefsOf(target)
  const prefix = `${fromNode}:`
  let changed = false
  for (const key of Object.keys(inputs)) {
    if (typeof inputs[key] === 'string' && (inputs[key] as string).startsWith(prefix)) {
      delete inputs[key]
      changed = true
    }
  }
  if (!changed) return
  target.params = { ...target.params, inputs }
}

/* ---------- delta 构造（write 调 workflowApi；read 权威读回该项；compensate 仅恢复该项） ---------- */

function nodeUpsertDelta(
  projectId: number,
  definitionId: number,
  previous: DraftNodeOrNull,
  next: WorkflowDraftNode,
): WorkflowSaveDelta<DraftNodeOrNull> {
  return {
    key: `node:${next.nodeCode}`,
    previous,
    next,
    async write(value) {
      await upsertWorkflowDraftNode(projectId, definitionId, value as WorkflowDraftNode)
    },
    async read() {
      const draft = (await getWorkflowDefinition(projectId, definitionId)).draft
      return draft.nodes.find((n) => n.nodeCode === next.nodeCode) ?? null
    },
    async compensate(previous) {
      if (previous === null) await deleteWorkflowDraftNode(projectId, definitionId, next.nodeCode)
      else await upsertWorkflowDraftNode(projectId, definitionId, previous)
    },
    equals: (actual, expected) => serializeNode(actual) === serializeNode(expected),
  }
}

function nodeDeleteDelta(
  projectId: number,
  definitionId: number,
  previous: WorkflowDraftNode,
): WorkflowSaveDelta<DraftNodeOrNull> {
  const next = null
  return {
    key: `node-del:${previous.nodeCode}`,
    previous,
    next,
    async write() {
      await deleteWorkflowDraftNode(projectId, definitionId, previous.nodeCode)
    },
    async read() {
      const draft = (await getWorkflowDefinition(projectId, definitionId)).draft
      return draft.nodes.find((n) => n.nodeCode === previous.nodeCode) ?? null
    },
    async compensate(prev) {
      await upsertWorkflowDraftNode(projectId, definitionId, prev as WorkflowDraftNode)
    },
    equals: (actual, expected) => serializeNode(actual) === serializeNode(expected),
  }
}

function edgeUpsertDelta(
  projectId: number,
  definitionId: number,
  previous: WorkflowDraftEdge | null,
  next: WorkflowDraftEdge,
): WorkflowSaveDelta<WorkflowDraftEdge | null> {
  return {
    key: `edge:${edgeKey(next)}`,
    previous,
    next,
    async write(value) {
      await upsertWorkflowDraftEdge(projectId, definitionId, value as WorkflowDraftEdge)
    },
    async read() {
      const draft = (await getWorkflowDefinition(projectId, definitionId)).draft
      return draft.edges.find((e) => edgeKey(e) === edgeKey(next)) ?? null
    },
    async compensate(prev) {
      if (prev === null) await deleteWorkflowDraftEdge(projectId, definitionId, next.fromNode, next.toNode)
      else await upsertWorkflowDraftEdge(projectId, definitionId, prev)
    },
    equals: (actual, expected) => serializeEdge(actual) === serializeEdge(expected),
  }
}

function edgeDeleteDelta(
  projectId: number,
  definitionId: number,
  previous: WorkflowDraftEdge,
): WorkflowSaveDelta<WorkflowDraftEdge | null> {
  const next = null
  return {
    key: `edge-del:${edgeKey(previous)}`,
    previous,
    next,
    async write() {
      await deleteWorkflowDraftEdge(projectId, definitionId, previous.fromNode, previous.toNode)
    },
    async read() {
      const draft = (await getWorkflowDefinition(projectId, definitionId)).draft
      return draft.edges.find((e) => edgeKey(e) === edgeKey(previous)) ?? null
    },
    async compensate(prev) {
      await upsertWorkflowDraftEdge(projectId, definitionId, prev as WorkflowDraftEdge)
    },
    equals: (actual, expected) => serializeEdge(actual) === serializeEdge(expected),
  }
}

/** diff baseline vs 当前 → 安全序 deltas（删边 → 删节点 → upsert 节点 → upsert 边） */
function diffGraph(
  projectId: number,
  definitionId: number,
  baselineNodes: WorkflowDraftNode[],
  baselineEdges: WorkflowDraftEdge[],
  nodes: WorkflowDraftNode[],
  edges: WorkflowDraftEdge[],
): WorkflowSaveDelta<DraftNodeOrNull | WorkflowDraftEdge | null>[] {
  const deltas: ReturnType<typeof diffGraph> = []
  const baseNodes = new Map(baselineNodes.map((n) => [n.nodeCode, n]))
  const curNodes = new Map(nodes.map((n) => [n.nodeCode, n]))
  const baseEdges = new Map(baselineEdges.map((e) => [edgeKey(e), e]))
  const curEdges = new Map(edges.map((e) => [edgeKey(e), e]))

  for (const [key, prev] of baseEdges) {
    if (!curEdges.has(key)) deltas.push(edgeDeleteDelta(projectId, definitionId, prev))
  }
  for (const [code, prev] of baseNodes) {
    if (!curNodes.has(code)) deltas.push(nodeDeleteDelta(projectId, definitionId, prev))
  }
  for (const node of nodes) {
    const prev = baseNodes.get(node.nodeCode) ?? null
    if (!prev || serializeNode(prev) !== serializeNode(node)) {
      deltas.push(nodeUpsertDelta(projectId, definitionId, prev, node))
    }
  }
  for (const edge of edges) {
    const prev = baseEdges.get(edgeKey(edge)) ?? null
    if (!prev || serializeEdge(prev) !== serializeEdge(edge)) {
      deltas.push(edgeUpsertDelta(projectId, definitionId, prev, edge))
    }
  }
  return deltas
}

/* ---------- store ---------- */

/** 单实例串行化该 store 全部保存批（多 Tab 切换不并发写同一 draft） */
const saveQueue = new WorkflowSaveQueue()

export const useWorkflowGraphStore = defineStore('workflowGraph', {
  state: () => ({
    docId: null as number | null,
    projectId: null as number | null,
    name: '',
    nodes: [] as WorkflowDraftNode[],
    edges: [] as WorkflowDraftEdge[],
    baseline: null as { nodes: WorkflowDraftNode[]; edges: WorkflowDraftEdge[] } | null,
    loading: false,
    loadingDefinitionId: null as number | null,
    loadSeq: 0,
    lastError: null as string | null,
    lastSaveResult: null as WorkflowSaveResult | null,
  }),

  getters: {
    /** 宿主接驳面（TaskCenterView onCloseTab：graphStore.doc?.id === t.docId） */
    doc(state): { id: number; projectId: number; name: string } | null {
      if (state.docId === null || state.projectId === null) return null
      return { id: state.docId, projectId: state.projectId, name: state.name }
    },
    isDirty(state): boolean {
      if (!state.baseline) return false
      return graphDiffers(state.baseline.nodes, state.baseline.edges, state.nodes, state.edges)
    },
  },

  actions: {
    /** 回读 draft 并锚定 baseline；loadSeq 守卫：仅最新响应落地（过期响应/错误丢弃） */
    async load(projectId: number, definitionId: number): Promise<void> {
      const seq = ++this.loadSeq
      this.loading = true
      this.loadingDefinitionId = definitionId
      this.lastError = null
      try {
        const info = await getWorkflowDefinition(projectId, definitionId)
        if (seq !== this.loadSeq) return
        this.projectId = projectId
        this.docId = definitionId
        this.name = info.name
        this.nodes = info.draft.nodes
        this.edges = info.draft.edges
        this.baseline = snapshot(info.draft.nodes, info.draft.edges)
      } catch (error) {
        if (seq !== this.loadSeq) return
        this.lastError = error instanceof Error ? error.message : String(error)
      } finally {
        if (seq === this.loadSeq) {
          this.loading = false
          this.loadingDefinitionId = null
        }
      }
    },

    addNode(input: {
      nodeType: WfNodeType
      name?: string | null
      params?: Record<string, unknown> | null
      componentRef?: { type: string; version: number }
      positionX?: number | null
      positionY?: number | null
    }): WorkflowDraftNode {
      const node: WorkflowDraftNode = {
        nodeCode: nextNodeCode(this.nodes),
        nodeType: input.nodeType,
        name: input.name ?? null,
        params: input.params ?? null,
        ...(input.componentRef ? { componentRef: input.componentRef } : {}),
        positionX: input.positionX ?? null,
        positionY: input.positionY ?? null,
      }
      this.nodes.push(node)
      return node
    },

    /** 本地级联删触边（服务端 nodes/delete 同语义；diff 派发删除 delta）；
     *  被 source 端删除触发的触边同步回收 target 的 inputs 引用 */
    removeNode(nodeCode: string): void {
      const idx = this.nodes.findIndex((n) => n.nodeCode === nodeCode)
      if (idx === -1) return
      const downstreamTargets = [...new Set(this.edges.filter((e) => e.fromNode === nodeCode).map((e) => e.toNode))]
      this.nodes.splice(idx, 1)
      this.edges = this.edges.filter((e) => e.fromNode !== nodeCode && e.toNode !== nodeCode)
      for (const target of downstreamTargets) pruneInputRefs(this.nodes, target, nodeCode)
    },

    updateNode(
      nodeCode: string,
      patch: {
        name?: string | null
        params?: Record<string, unknown> | null
        positionX?: number | null
        positionY?: number | null
      },
    ): void {
      const node = this.nodes.find((n) => n.nodeCode === nodeCode)
      if (!node) return
      if (patch.name !== undefined) node.name = patch.name
      if (patch.params !== undefined) node.params = patch.params
      if (patch.positionX !== undefined) node.positionX = patch.positionX
      if (patch.positionY !== undefined) node.positionY = patch.positionY
    },

    moveNode(nodeCode: string, x: number, y: number): void {
      this.updateNode(nodeCode, { positionX: x, positionY: y })
    },

    /** (from,to) 身份幂等：已存在或自环 → null 不加 */
    addEdge(fromNode: string, toNode: string, name?: string | null): WorkflowDraftEdge | null {
      // Reject dangling connections locally; Vue Flow may emit a connection
      // while a node is being removed, and the backend would reject it later.
      if (!this.nodes.some((n) => n.nodeCode === fromNode) || !this.nodes.some((n) => n.nodeCode === toNode)) return null
      if (fromNode === toNode) return null
      if (this.edges.some((e) => e.fromNode === fromNode && e.toNode === toNode)) return null
      // A design workflow is a DAG. Adding from->to is cyclic when `to`
      // already reaches `from` through the current draft.
      const outgoing = new Map<string, string[]>()
      for (const edge of this.edges) {
        const next = outgoing.get(edge.fromNode) ?? []
        next.push(edge.toNode)
        outgoing.set(edge.fromNode, next)
      }
      const pending = [toNode]
      const seen = new Set<string>()
      while (pending.length) {
        const current = pending.pop()!
        if (current === fromNode) return null
        if (seen.has(current)) continue
        seen.add(current)
        pending.push(...(outgoing.get(current) ?? []))
      }
      const edge: WorkflowDraftEdge = { fromNode, toNode, name: name ?? null }
      this.edges.push(edge)
      // T3 拖边即引用：边即具名引用（nodeId:port），派生进 target params.inputs；
      // port 约定 source 端 ':out'（spec 未定义 ports 时的默认端口）
      deriveInputRef(this.nodes, toNode, fromNode)
      return edge
    },

    removeEdge(fromNode: string, toNode: string): void {
      const existed = this.edges.some((e) => e.fromNode === fromNode && e.toNode === toNode)
      this.edges = this.edges.filter((e) => !(e.fromNode === fromNode && e.toNode === toNode))
      if (existed) pruneInputRefs(this.nodes, toNode, fromNode)
    },

    /**
     * diff → SaveQueue.save（R-25）。无差异直接收口（幂等，不发请求）；
     * complete → baseline=当前；部分失败 → baseline 不动（isDirty 保持 true 可重试）。
     */
    async save(): Promise<WorkflowSaveResult | null> {
      if (this.docId === null || this.projectId === null || !this.baseline) return null
      const deltas = diffGraph(
        this.projectId, this.docId,
        this.baseline.nodes, this.baseline.edges,
        this.nodes, this.edges,
      )
      if (deltas.length === 0) {
        this.baseline = snapshot(this.nodes, this.edges)
        return { outcomes: [], savedKeys: [], dirtyKeys: [], manualRecoveryKeys: [], complete: true }
      }
      const result = await saveQueue.save(deltas)
      this.lastSaveResult = result
      if (result.complete) {
        this.baseline = snapshot(this.nodes, this.edges)
        this.lastError = null
      } else {
        this.lastError = `save incomplete: ${result.dirtyKeys.join(', ')}`
      }
      return result
    },

    /** 宿主关 Tab 时调用：docId 匹配才清态（不匹配不动） */
    close(definitionId: number): void {
      if (this.docId !== definitionId && this.loadingDefinitionId !== definitionId) return
      this.loadSeq += 1
      this.loading = false
      this.loadingDefinitionId = null
      this.docId = null
      this.projectId = null
      this.name = ''
      this.nodes = []
      this.edges = []
      this.baseline = null
      this.lastSaveResult = null
      this.lastError = null
    },
  },
})
