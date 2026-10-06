/**
 * 错误聚合模型（工作台优化 Task 10，方案 §3.3）。
 * - issuesToSources：既有 Issue[]（profile validators + Task 8 edgeTypeIssues）→ 三类错误源，
 *   level 全链路透传（红描边 / Inspector 卡片 / badge 只认 error 级；warn 仅进面板琥珀提示）。
 *   分类规则：有 edgeId → edge（Task 8 双 id 场景以 edgeId 优先）；否则有 nodeId → node；皆无 → gate。
 * - collectDocErrors：三类错误源 → 统一 DocError 列表（面板三页签 + 定位锚点），level 缺省 'error'。
 * 均为纯函数：GraphWorkbench 以 computed 从 doc 实时聚合，修复后计数/红描边自动消失。
 */
import type { Issue, IssueLevel } from './index'

/** 统一错误条目：kind 决定页签；nodeId/edgeId 为定位锚点（gate 无锚点不显示定位按钮）；level 驱动面板配色与红描边口径 */
export interface DocError {
  kind: 'node' | 'edge' | 'gate'
  level: IssueLevel
  nodeId?: string
  edgeId?: string
  code: string
  message: string
}

/** node 错误源条目：字符串（缺省 error）或带 level 的对象（issuesToSources 输出后者） */
export type NodeErrorItem = string | { message: string; level?: IssueLevel }

/** 三类错误源（collectDocErrors 入参形状），level 可选缺省 error */
export interface ErrorSources {
  nodeErrors: Record<string, NodeErrorItem[]>
  edgeErrors: { edgeId: string; message: string; level?: IssueLevel }[]
  gateErrors: { code: string; message: string; level?: IssueLevel }[]
}

export function collectDocErrors(
  _doc: { nodes: { id: string }[]; edges: unknown[] },
  src: ErrorSources,
): DocError[] {
  const out: DocError[] = []
  for (const [nodeId, msgs] of Object.entries(src.nodeErrors)) {
    for (const m of msgs) {
      const item = typeof m === 'string' ? { message: m, level: 'error' as IssueLevel } : m
      out.push({ kind: 'node', level: item.level ?? 'error', nodeId, code: 'NODE_INVALID', message: item.message })
    }
  }
  for (const e of src.edgeErrors) out.push({ kind: 'edge', level: e.level ?? 'error', edgeId: e.edgeId, code: 'EDGE_INVALID', message: e.message })
  for (const g of src.gateErrors) out.push({ kind: 'gate', level: g.level ?? 'error', code: g.code, message: g.message })
  return out
}

export function issuesToSources(issues: Issue[]): ErrorSources {
  const src: ErrorSources = { nodeErrors: {}, edgeErrors: [], gateErrors: [] }
  for (const it of issues) {
    if (it.edgeId) src.edgeErrors.push({ edgeId: it.edgeId, message: it.msg, level: it.level })
    else if (it.nodeId) (src.nodeErrors[it.nodeId] ??= []).push({ message: it.msg, level: it.level })
    else src.gateErrors.push({ code: 'GATE_INVALID', message: it.msg, level: it.level })
  }
  return src
}
