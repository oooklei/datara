/**
 * W1 画布校验器（T4/G07）：11 个 validators 纯函数集，保存闸门与校验面板共用语义。
 *
 * 口径对齐（datara 自研试运行域已废弃，画布保存闸门语义由本模块单一承载）：
 *  - 组件图（无 START/END）免 root/leaf 检查但要求全图连通；legacy 图（含任一 START/END）
 *    要求 START/END 兼备、非 START 必有入边、非 END 必有出边；成环、断链边一律 error；
 *    DEPENDENT 缺 dependency_id 为设计态占位放行。
 *  - 旧前端 dag.ts validators（交互语义补充）：重复边 warn、必填缺失 warn、end 禁出边 error。
 *  - 组件级约束与上游依赖合法性消费 1.9 活体 spec（specForm.ts）：constraints.requiredIf、
 *    form.inputs cap.mode=upstreamOutputs（required→入边≥1；max→入边≤max）。
 * specs 缺失时 spec 驱动的两项（CONSTRAINT/UPSTREAM_DEP）优雅跳过，图结构校验不受影响。
 */
import type { ComponentSpecItem } from '../services/rebuild/componentSpecApi'
import { constraintViolations, isRecord, sectionOf } from '../services/rebuild/specForm'

export type ValidationLevel = 'error' | 'warn'

export interface ValidationIssue {
  level: ValidationLevel
  code:
    | 'CYCLE' | 'BROKEN_EDGE' | 'START_END' | 'ORPHAN' | 'DUPLICATE_EDGE'
    | 'STREAM_SUBGRAPH' | 'REQUIRED_MISSING' | 'END_OUTGOING'
    | 'CONSTRAINT' | 'BRANCH' | 'UPSTREAM_DEP'
  msg: string
  nodeCode?: string
}

export interface ValidatorNode {
  nodeCode: string
  nodeType: string
  name?: string | null
  params?: Record<string, unknown> | null
}

export interface ValidatorEdge {
  fromNode: string
  toNode: string
}

const STREAM_TYPES = new Set(['stream_input', 'stream_fuse', 'stream_output'])
const STREAM_DISPLAY_TYPES = new Set(['page_board'])
const CONDITIONAL_TYPES = new Set(['condition_set'])

export function nodeLabel(node: ValidatorNode): string {
  return `${node.nodeCode}${node.name ? `（${node.name}）` : ''}`
}

/** T2 configure-first 判定（组件工作台共用单源）：设计态组件节点业务参数（除
 *  component 归属标记、inputs 结构派生引用外）全空即未配置；START/END 等
 *  非设计态类型恒视为已配置（不参与判定） */
export function isNodeUnconfigured(node: ValidatorNode, designTypes: ReadonlySet<string>): boolean {
  if (!designTypes.has(node.nodeType)) return false
  const params = node.params ?? {}
  return !Object.keys(params).some((key) => key !== 'component' && key !== 'inputs')
}

/** 1. 成环检测（DFS，报环路径） */
export function detectCycle(nodes: readonly ValidatorNode[], edges: readonly ValidatorEdge[]): ValidationIssue[] {
  const adjacency = new Map<string, string[]>()
  for (const node of nodes) adjacency.set(node.nodeCode, [])
  for (const edge of edges) {
    if (adjacency.has(edge.fromNode) && adjacency.has(edge.toNode)) adjacency.get(edge.fromNode)!.push(edge.toNode)
  }
  const state = new Map<string, 0 | 1 | 2>() // 0=未访 1=在栈 2=完成
  for (const node of nodes) state.set(node.nodeCode, 0)

  const path: string[] = []
  const visit = (code: string): string[] | null => {
    state.set(code, 1)
    path.push(code)
    for (const next of adjacency.get(code) ?? []) {
      const s = state.get(next)
      if (s === 1) return [...path.slice(path.indexOf(next)), next]
      if (s === 0) {
        const found = visit(next)
        if (found) return found
      }
    }
    path.pop()
    state.set(code, 2)
    return null
  }
  for (const node of nodes) {
    if (state.get(node.nodeCode) !== 0) continue
    const found = visit(node.nodeCode)
    if (!found) continue
    const names = found.slice(0, -1).map((code) => nodeLabel(nodes.find((n) => n.nodeCode === code) ?? { nodeCode: code, nodeType: '' }))
    return [{ level: 'error', code: 'CYCLE', msg: `依赖存在环：${names.join(' → ')}（DAG 不允许成环）`, nodeCode: found[0] }]
  }
  return []
}

/** 2. 断链（边引用不存在的节点） */
export function brokenEdgeIssues(nodes: readonly ValidatorNode[], edges: readonly ValidatorEdge[]): ValidationIssue[] {
  const codes = new Set(nodes.map((n) => n.nodeCode))
  return edges
    .filter((edge) => !codes.has(edge.fromNode) || !codes.has(edge.toNode))
    .map((edge) => ({
      level: 'error' as const,
      code: 'BROKEN_EDGE' as const,
      msg: `连线 ${edge.fromNode} → ${edge.toNode} 引用了不存在的节点（断链）`,
      nodeCode: codes.has(edge.fromNode) ? edge.toNode : edge.fromNode,
    }))
}

/** 3. START/END 兼备与唯一（legacy 图口径；组件图全无则合法） */
export function startEndIssues(nodes: readonly ValidatorNode[]): ValidationIssue[] {
  const starts = nodes.filter((n) => n.nodeType === 'START')
  const ends = nodes.filter((n) => n.nodeType === 'END')
  const isComponentGraph = starts.length === 0 && ends.length === 0
  if (isComponentGraph) return []
  const issues: ValidationIssue[] = []
  if (starts.length === 0) issues.push({ level: 'error', code: 'START_END', msg: '缺少「开始」（START）节点' })
  if (ends.length === 0) issues.push({ level: 'error', code: 'START_END', msg: '缺少「结束」（END）节点' })
  if (starts.length > 1) {
    issues.push({ level: 'error', code: 'START_END', msg: `「开始」节点只能有一个（当前 ${starts.length}）`, nodeCode: starts[1].nodeCode })
  }
  if (ends.length > 1) {
    issues.push({ level: 'error', code: 'START_END', msg: `「结束」节点只能有一个（当前 ${ends.length}）`, nodeCode: ends[1].nodeCode })
  }
  return issues
}

/** 4. 孤立/连通：legacy 图非 START 无入边、非 END 无出边 error；组件图从根不可达 error */
export function orphanIssues(nodes: readonly ValidatorNode[], edges: readonly ValidatorEdge[]): ValidationIssue[] {
  if (nodes.length === 0) return []
  const incoming = new Map<string, number>()
  const outgoing = new Map<string, number>()
  for (const node of nodes) {
    incoming.set(node.nodeCode, 0)
    outgoing.set(node.nodeCode, 0)
  }
  for (const edge of edges) {
    if (incoming.has(edge.toNode)) incoming.set(edge.toNode, incoming.get(edge.toNode)! + 1)
    if (outgoing.has(edge.fromNode)) outgoing.set(edge.fromNode, outgoing.get(edge.fromNode)! + 1)
  }
  const hasLegacy = nodes.some((n) => n.nodeType === 'START' || n.nodeType === 'END')
  if (hasLegacy) {
    return nodes.flatMap((node) => {
      const issues: ValidationIssue[] = []
      if (node.nodeType !== 'START' && incoming.get(node.nodeCode) === 0) {
        issues.push({ level: 'error', code: 'ORPHAN', msg: `「${nodeLabel(node)}」无入边（orphan）`, nodeCode: node.nodeCode })
      }
      if (node.nodeType !== 'END' && outgoing.get(node.nodeCode) === 0) {
        issues.push({ level: 'error', code: 'ORPHAN', msg: `「${nodeLabel(node)}」无出边（orphan）`, nodeCode: node.nodeCode })
      }
      return issues
    })
  }
  // 组件图：root BFS 全图连通（后端 disconnected 口径）；全无连接的孤立节点 warn
  // （对齐旧前端孤立节点告警语义；后端将其视为 root 放行，故不升 error）
  const adjacency = new Map<string, string[]>()
  for (const node of nodes) adjacency.set(node.nodeCode, [])
  for (const edge of edges) adjacency.get(edge.fromNode)?.push(edge.toNode)
  const reachable = new Set<string>()
  const frontier = nodes.filter((n) => incoming.get(n.nodeCode) === 0).map((n) => n.nodeCode)
  frontier.forEach((code) => reachable.add(code))
  while (frontier.length) {
    const code = frontier.pop()!
    for (const next of adjacency.get(code) ?? []) {
      if (!reachable.has(next)) {
        reachable.add(next)
        frontier.push(next)
      }
    }
  }
  return [
    ...nodes
      .filter((node) => !reachable.has(node.nodeCode))
      .map((node) => ({ level: 'error' as const, code: 'ORPHAN' as const, msg: `「${nodeLabel(node)}」未接入流程（不可达）`, nodeCode: node.nodeCode })),
    ...nodes
      .filter((node) => incoming.get(node.nodeCode) === 0 && outgoing.get(node.nodeCode) === 0)
      .map((node) => ({ level: 'warn' as const, code: 'ORPHAN' as const, msg: `「${nodeLabel(node)}」孤立节点未接入流程`, nodeCode: node.nodeCode })),
  ]
}

/** 5. 重复边（同 from→to 多条） */
export function duplicateEdgeIssues(edges: readonly ValidatorEdge[]): ValidationIssue[] {
  const seen = new Set<string>()
  const issues: ValidationIssue[] = []
  for (const edge of edges) {
    const key = `${edge.fromNode}->${edge.toNode}`
    if (seen.has(key)) {
      issues.push({ level: 'warn', code: 'DUPLICATE_EDGE', msg: `存在重复依赖边 ${key}`, nodeCode: edge.fromNode })
    }
    seen.add(key)
  }
  return issues
}

/** 6. 流子图完整性（C18~C20）：混编/缺源汇/join 两路/游离 */
export function streamSubgraphIssues(nodes: readonly ValidatorNode[], edges: readonly ValidatorEdge[]): ValidationIssue[] {
  const streamNodes = nodes.filter((n) => STREAM_TYPES.has(n.nodeType))
  if (!streamNodes.length) return []
  const issues: ValidationIssue[] = []
  const mixed = nodes.filter((n) => !STREAM_TYPES.has(n.nodeType) && !STREAM_DISPLAY_TYPES.has(n.nodeType)
    && n.nodeType !== 'START' && n.nodeType !== 'END')
  if (mixed.length) {
    issues.push({
      level: 'error',
      code: 'STREAM_SUBGRAPH',
      msg: `流组件与批处理组件不可混编（${mixed.map(nodeLabel).join('、')}），请拆分画布`,
      nodeCode: mixed[0].nodeCode,
    })
  }
  if (!streamNodes.some((n) => n.nodeType === 'stream_input')) {
    issues.push({ level: 'error', code: 'STREAM_SUBGRAPH', msg: '流子图缺少「流输入」（stream_input）节点' })
  }
  if (!streamNodes.some((n) => n.nodeType === 'stream_output')) {
    issues.push({ level: 'error', code: 'STREAM_SUBGRAPH', msg: '流子图缺少「流输出」（stream_output）节点' })
  }
  for (const node of streamNodes) {
    const inDeg = edges.filter((e) => e.toNode === node.nodeCode).length
    const outDeg = edges.filter((e) => e.fromNode === node.nodeCode).length
    if (node.nodeType === 'stream_fuse' && String(node.params?.fuseType ?? 'window') === 'join' && inDeg < 2) {
      issues.push({ level: 'error', code: 'STREAM_SUBGRAPH', msg: `「${nodeLabel(node)}」join 融合须接入两路流（当前 ${inDeg} 条入边）`, nodeCode: node.nodeCode })
    }
    if (node.nodeType !== 'stream_input' && inDeg === 0) {
      issues.push({ level: 'error', code: 'STREAM_SUBGRAPH', msg: `「${nodeLabel(node)}」未接入上游流（游离节点）`, nodeCode: node.nodeCode })
    }
    if (node.nodeType !== 'stream_output' && outDeg === 0) {
      issues.push({ level: 'error', code: 'STREAM_SUBGRAPH', msg: `「${nodeLabel(node)}」未连接下游流组件`, nodeCode: node.nodeCode })
    }
  }
  return issues
}

/** 7. 必填缺失（configure-first 共用判定，warn 级：拦截由 T2 闸门负责） */
export function requiredMissingIssues(nodes: readonly ValidatorNode[], designTypes: ReadonlySet<string>): ValidationIssue[] {
  return nodes
    .filter((node) => isNodeUnconfigured(node, designTypes))
    .map((node) => ({ level: 'warn' as const, code: 'REQUIRED_MISSING' as const, msg: `「${nodeLabel(node)}」必填项未配置`, nodeCode: node.nodeCode }))
}

/** 8. END 禁止出边 */
export function endOutgoingIssues(nodes: readonly ValidatorNode[], edges: readonly ValidatorEdge[]): ValidationIssue[] {
  return nodes
    .filter((node) => node.nodeType === 'END')
    .flatMap((node) => {
      const out = edges.filter((e) => e.fromNode === node.nodeCode)
      return out.length
        ? [{ level: 'error' as const, code: 'END_OUTGOING' as const, msg: `「${nodeLabel(node)}」是结束节点，禁止连出边（当前 ${out.length} 条出边）`, nodeCode: node.nodeCode }]
        : []
    })
}

/** 9. 组件级校验：spec constraints.requiredIf 求值（活体 spec；spec 缺失跳过） */
export function constraintIssues(nodes: readonly ValidatorNode[], specs: ReadonlyMap<string, ComponentSpecItem>): ValidationIssue[] {
  return nodes.flatMap((node) => {
    const spec = specs.get(node.nodeType)
    if (!spec) return []
    return constraintViolations(spec, node.params).map((rule) => ({
      level: 'error' as const,
      code: 'CONSTRAINT' as const,
      msg: `「${nodeLabel(node)}」约束未满足：${rule.msg ?? `${rule.field} 必填`}`,
      nodeCode: node.nodeCode,
    }))
  })
}

/** 10. 分支完整性（rebuild 口径）：条件类组件（condition_set）应连接下游（warn，不阻断） */
export function branchIssues(nodes: readonly ValidatorNode[], edges: readonly ValidatorEdge[]): ValidationIssue[] {
  return nodes
    .filter((node) => CONDITIONAL_TYPES.has(node.nodeType))
    .flatMap((node) => (edges.some((e) => e.fromNode === node.nodeCode)
      ? []
      : [{ level: 'warn' as const, code: 'BRANCH' as const, msg: `「${nodeLabel(node)}」未连接下游分支`, nodeCode: node.nodeCode }]))
}

/** 11. 依赖合法性：spec form.inputs 声明 cap.mode=upstreamOutputs 的上游输入
 *  （required→入边≥1；cap.max→入边≤max；spec 缺失跳过） */
export function upstreamDepIssues(nodes: readonly ValidatorNode[], edges: readonly ValidatorEdge[], specs: ReadonlyMap<string, ComponentSpecItem>): ValidationIssue[] {
  return nodes.flatMap((node) => {
    const spec = specs.get(node.nodeType)
    if (!spec) return []
    const inDeg = edges.filter((e) => e.toNode === node.nodeCode).length
    return sectionOf(spec, 'inputs').flatMap((raw) => {
      if (!isRecord(raw)) return []
      const cap = isRecord(raw.cap) ? raw.cap : null
      if (cap?.mode !== 'upstreamOutputs') return []
      const issues: ValidationIssue[] = []
      if (raw.required === true && inDeg < 1) {
        issues.push({ level: 'error', code: 'UPSTREAM_DEP', msg: `「${nodeLabel(node)}」缺少上游输入依赖（${String(raw.label ?? raw.key ?? 'inputs')}）`, nodeCode: node.nodeCode })
      }
      if (typeof cap.max === 'number' && inDeg > cap.max) {
        issues.push({ level: 'error', code: 'UPSTREAM_DEP', msg: `「${nodeLabel(node)}」上游输入超过上限 ${cap.max}（当前 ${inDeg}）`, nodeCode: node.nodeCode })
      }
      return issues
    })
  })
}

/** 11 validators 汇总入口（保存闸门/校验面板共用） */
export function validateWorkflowDraft(
  nodes: readonly ValidatorNode[],
  edges: readonly ValidatorEdge[],
  options: {
    specs?: ReadonlyMap<string, ComponentSpecItem>
    designTypes?: ReadonlySet<string>
  } = {},
): ValidationIssue[] {
  const specs = options.specs ?? new Map<string, ComponentSpecItem>()
  const designTypes = options.designTypes ?? new Set<string>()
  return [
    ...detectCycle(nodes, edges),
    ...brokenEdgeIssues(nodes, edges),
    ...startEndIssues(nodes),
    ...orphanIssues(nodes, edges),
    ...duplicateEdgeIssues(edges),
    ...streamSubgraphIssues(nodes, edges),
    ...requiredMissingIssues(nodes, designTypes),
    ...endOutgoingIssues(nodes, edges),
    ...constraintIssues(nodes, specs),
    ...branchIssues(nodes, edges),
    ...upstreamDepIssues(nodes, edges, specs),
  ]
}
