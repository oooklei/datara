/**
 * 错误聚合模型（工作台优化 Task 10，方案 §3.3）。
 * - issuesToSources：既有 Issue[]（profile validators + Task 8 edgeTypeIssues）→ 三类错误源。
 *   分类规则：有 edgeId → edge（Task 8 双 id 场景以 edgeId 优先）；否则有 nodeId → node；皆无 → gate。
 *   纯机械分类，不做 level 过滤（warn 级同样进面板，由列表语义自明）。
 * - collectDocErrors：三类错误源 → 统一 DocError 列表（面板三页签 + 定位锚点）。
 * 均为纯函数：GraphWorkbench 以 computed 从 doc 实时聚合，修复后计数/红描边自动消失。
 */
import type { Issue } from './index'

/** 统一错误条目：kind 决定页签；nodeId/edgeId 为定位锚点（gate 无锚点不显示定位按钮） */
export interface DocError {
  kind: 'node' | 'edge' | 'gate'
  nodeId?: string
  edgeId?: string
  code: string
  message: string
}

/** 三类错误源（collectDocErrors 入参形状） */
export interface ErrorSources {
  nodeErrors: Record<string, string[]>
  edgeErrors: { edgeId: string; message: string }[]
  gateErrors: { code: string; message: string }[]
}

export function collectDocErrors(
  _doc: { nodes: { id: string }[]; edges: unknown[] },
  src: ErrorSources,
): DocError[] {
  const out: DocError[] = []
  for (const [nodeId, msgs] of Object.entries(src.nodeErrors)) {
    for (const m of msgs) out.push({ kind: 'node', nodeId, code: 'NODE_INVALID', message: m })
  }
  for (const e of src.edgeErrors) out.push({ kind: 'edge', edgeId: e.edgeId, code: 'EDGE_INVALID', message: e.message })
  for (const g of src.gateErrors) out.push({ kind: 'gate', code: g.code, message: g.message })
  return out
}

export function issuesToSources(issues: Issue[]): ErrorSources {
  const src: ErrorSources = { nodeErrors: {}, edgeErrors: [], gateErrors: [] }
  for (const it of issues) {
    if (it.edgeId) src.edgeErrors.push({ edgeId: it.edgeId, message: it.msg })
    else if (it.nodeId) (src.nodeErrors[it.nodeId] ??= []).push(it.msg)
    else src.gateErrors.push({ code: 'GATE_INVALID', message: it.msg })
  }
  return src
}
