/**
 * 连线四道闸（工作台优化 Task 8，方案 §3.1）：①自连 → ②重复边 → ③成环 → ④类型交集。
 * 纯函数，禁止依赖 store/service；端口类型由调用方解析后经 portTypes 传入
 * （GraphWorkbench：spec 命中取 SpecPort.type，profile 形态/handle 匹配不到 → 缺省 = any 恒放行）。
 */
import type { GraphDocument } from './index'
import { detectCycle } from './index'
import { portTypesMatch } from './portTypes'

/** 待校验连线（vue-flow Connection / GEdge 均可直传：handle 缺省与 null 等价） */
export interface ConnSpec {
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
}

/** 端口类型提示：src/dst 任一缺省或未知类型按 any 处理（portTypesMatch 恒真，不误拦） */
export interface PortTypesHint {
  src?: string
  dst?: string
}

/** 闸门选项：checkCycle=false 跳过成环预检（非 DAG 布局视角保持旧行为） */
export interface ConnectionGuardOptions {
  checkCycle?: boolean
}

/**
 * 四道闸顺序校验，返回拒绝原因（null = 放行）：
 * ① 自连「不允许自连」；② 重复边——同 source+target+sourceHandle（不同分支端点到同一
 * 目标不算重复）「依赖边已存在」；③ 成环——detectCycle 预检「该连接将形成环（DAG 不允许成环）」；
 * ④ 类型交集——portTypes 提供时才判「类型不匹配：源 X → 目标 Y」。
 */
export function connectionRejectReason(
  doc: GraphDocument,
  conn: ConnSpec,
  portTypes?: PortTypesHint,
  options?: ConnectionGuardOptions,
): string | null {
  if (conn.source === conn.target) return '不允许自连'
  const sh = conn.sourceHandle ?? ''
  if (doc.edges.some((e) => e.source === conn.source && e.target === conn.target && (e.sourceHandle ?? '') === sh)) {
    return '依赖边已存在'
  }
  if (options?.checkCycle !== false) {
    const next: GraphDocument = {
      ...doc,
      edges: [...doc.edges, { id: '__pred__', source: conn.source, target: conn.target }],
    }
    if (detectCycle(next).length) return '该连接将形成环（DAG 不允许成环）'
  }
  if (portTypes && !portTypesMatch(portTypes.src, portTypes.dst)) {
    return `类型不匹配：源 ${portTypes.src} → 目标 ${portTypes.dst}`
  }
  return null
}
