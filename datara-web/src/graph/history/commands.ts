import type { GEdge, GNode, GraphDocument } from '../model'

export type GraphCommandKind = 'add-node' | 'delete-nodes' | 'move-nodes' | 'connect' | 'disconnect' | 'update-props'

/** A reversible, serializable-in-spirit graph edit. */
export interface GraphCommand {
  kind: GraphCommandKind
  apply(doc: GraphDocument): GraphDocument
  undo(doc: GraphDocument): GraphDocument
}

const copy = <T>(value: T): T => structuredClone(value)

/**
 * A command retains its before/after document boundaries.  This makes undo
 * deterministic for compound edits such as deleting a node plus its incident
 * edges and group membership, and prevents history from sharing mutable data
 * with the active document.
 */
function transition(kind: GraphCommandKind, before: GraphDocument, after: GraphDocument): GraphCommand {
  const beforeCopy = copy(before)
  const afterCopy = copy(after)
  return {
    kind,
    apply: () => copy(afterCopy),
    undo: () => copy(beforeCopy),
  }
}

export function addNodeCommand(doc: GraphDocument, node: GNode): GraphCommand {
  const after = copy(doc)
  after.nodes.push(copy(node))
  return transition('add-node', doc, after)
}

export function deleteNodesCommand(doc: GraphDocument, ids: readonly string[]): GraphCommand {
  const after = copy(doc)
  const removed = new Set(ids)
  after.nodes = after.nodes.filter((node) => !removed.has(node.id))
  after.edges = after.edges.filter((edge) => !removed.has(edge.source) && !removed.has(edge.target))
  if (after.groups) {
    after.groups = after.groups
      .map((group) => ({ ...group, nodeIds: group.nodeIds.filter((id) => !removed.has(id)) }))
      .filter((group) => group.nodeIds.length > 0)
  }
  return transition('delete-nodes', doc, after)
}

export function moveNodesCommand(
  doc: GraphDocument,
  positions: Readonly<Record<string, { x: number; y: number }>>,
): GraphCommand {
  const after = copy(doc)
  after.nodes = after.nodes.map((node) => positions[node.id]
    ? { ...node, position: copy(positions[node.id]!) }
    : node)
  return transition('move-nodes', doc, after)
}

export function connectCommand(doc: GraphDocument, edge: GEdge): GraphCommand {
  const after = copy(doc)
  after.edges.push(copy(edge))
  return transition('connect', doc, after)
}

export function disconnectCommand(doc: GraphDocument, edgeIds: readonly string[]): GraphCommand {
  const after = copy(doc)
  const removed = new Set(edgeIds)
  after.edges = after.edges.filter((edge) => !removed.has(edge.id))
  return transition('disconnect', doc, after)
}

export function updatePropsCommand(
  doc: GraphDocument,
  nodeId: string,
  props: Readonly<Record<string, unknown>>,
): GraphCommand {
  const after = copy(doc)
  after.nodes = after.nodes.map((node) => node.id === nodeId
    ? { ...node, data: { ...node.data, ...copy(props) } }
    : node)
  return transition('update-props', doc, after)
}

/**
 * Task 22（2e）：按「实际变更前后档」捕获命令。带联动副作用的变更（连线/断边同步目标节点
 * inputs 引用、删节点清组与引用等）重放工厂得到的 after 与运行档可能不一致，直接捕获真实
 * 前后档可保证 undo/redo 精确等价；GraphWorkbench 在变更点调用并压入 commandHistory。
 */
export function captureCommand(kind: GraphCommandKind, before: GraphDocument, after: GraphDocument): GraphCommand {
  return transition(kind, before, after)
}
