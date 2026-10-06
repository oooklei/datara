/**
 * 多选复制粘贴纯函数（工作台优化 Task 11，方案 §3.5）。
 * 快照形状由宿主 Ctrl+C 落（节点深拷贝 / 内部边仅存粘贴所需字段的浅拷贝）；粘贴时：
 * - 节点新 id 由调用方注入 nextId(type) 生成，位置整体 +offset，data structuredClone 深拷贝；
 * - 边仅保留两端都在快照节点集内的内部边并重映射端点，边 id 由模块级序号生成器自实现
 *   （模式仿 model/index.ts 的 uid；本模块不 import index，避免循环依赖）。
 */

/** 剪贴板节点快照（data 泛型：宿主传 GNodeData，粘贴结果原样带回，不丢类型） */
export interface ClipboardNode<D = Record<string, unknown>> {
  id: string
  type: string
  position: { x: number; y: number }
  data: D
}

/** 剪贴板边快照最小结构（kind 放宽为 string；粘贴结果经泛型 E 原样带回调用方窄类型） */
export interface ClipboardEdge {
  source: string
  target: string
  kind?: string
  label?: string
  sourceHandle?: string
  targetHandle?: string
}

/** 粘贴边 id 序号（模块级自实现，同会话内保证唯一：同毫秒多次粘贴也不撞） */
let eseq = 0
function pasteEdgeId(): string {
  eseq += 1
  return `e_paste_${Date.now().toString(36)}${eseq.toString(36)}`
}

/**
 * 粘贴快照：offset 默认 24（Ctrl+V），传 0 = 原位复制（Ctrl+D）。
 * 纯函数：不改传入快照；跨组件连线（任一端不在快照节点集）直接丢弃；
 * 返回 nodes（新 id + 偏移位置 + data 深拷贝）与 edges（重映射端点 + 模块级新 id）。
 */
export function pasteSelection<D, E extends ClipboardEdge>(
  copied: { nodes: ClipboardNode<D>[]; edges: E[] },
  nextId: (type: string) => string,
  offset = 24,
): { nodes: ClipboardNode<D>[]; edges: (E & { id: string })[] } {
  const idMap = new Map<string, string>()
  const nodes = copied.nodes.map((n) => {
    const id = nextId(n.type)
    idMap.set(n.id, id)
    return {
      id,
      type: n.type,
      position: { x: n.position.x + offset, y: n.position.y + offset },
      data: structuredClone(n.data),
    }
  })
  const inner = new Set(copied.nodes.map((n) => n.id))
  const edges = copied.edges
    .filter((e) => inner.has(e.source) && inner.has(e.target))
    .map((e) => ({
      ...e,
      id: pasteEdgeId(),
      source: idMap.get(e.source)!,
      target: idMap.get(e.target)!,
    }))
  return { nodes, edges }
}
